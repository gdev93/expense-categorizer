import logging
from dataclasses import dataclass
from typing import List, Dict, Any

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, QuerySet, Sum, Exists, OuterRef, Count
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView

from api.models import UploadFile, Transaction, Category, DefaultCategory
from api.forms import UploadFileForm
from api.tasks import process_upload
from processors.csv_structure_detector import CsvStructureDetector
from processors.expense_upload_processor import persist_uploaded_file
from processors.file_parsers import parse_uploaded_file, FileParserError


# --- Data Classes ---

@dataclass
class CsvProcessingResult:
    """Result of CSV processing operation"""
    upload_file: UploadFile | None
    rows_processed: int
    success: bool
    error_message: str = ""


@dataclass
class UploadStatistics:
    """Statistics for CSV uploads"""
    total_uploads: int
    total_size_bytes: int
    total_size_mb: float
    total_transactions: int


@dataclass
class UploadContext:
    """Context for upload form configuration"""
    max_file_size_mb: int
    allowed_formats: List[str]


@dataclass
class UploadItemDisplay:
    """Display data for a single upload item"""
    file_name: str
    upload_date: str
    file_size_display: str
    processing_time: int | None
    status: str
    row_count: int

def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


class UploadFileView(ListView, FormView):
    """
    Combined view for CSV file upload and display of upload history.

    Responsibilities:
    - Display upload form with configuration context
    - Validate and process uploaded CSV files
    - Display paginated list of user's uploads
    - Show upload statistics
    """
    # ListView attributes
    model = UploadFile
    context_object_name = 'recent_uploads'

    # FormView attributes
    form_class = UploadFileForm
    success_url = reverse_lazy('transactions_upload')

    # Shared attributes
    template_name = 'transactions/transactions_upload.html'

    def get_paginate_by(self, queryset):
        return self.request.GET.get('paginate_by', 25)

    def get_template_names(self):
        if self.request.headers.get('HX-Request') and self.request.headers.get('HX-Target') != 'main-content':
            return ['transactions/components/upload_list_htmx.html']
        return [self.template_name]

    def get_queryset(self):
        """Get uploads for the current user (ListView method)"""
        queryset = UploadFile.objects.filter(
            user=self.request.user
        ).select_related('user').prefetch_related('transactions').order_by('-upload_date')

        # Search by file name
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(file_name__icontains=search_query)

        # Filter by status
        status_filters = [sf for sf in self.request.GET.getlist('status') if sf]
        if status_filters:
            q_objects = Q()
            for sf in status_filters:
                if sf == 'ready':
                    q_objects |= Q(status='completed')
                elif sf == 'not_ready':
                    q_objects |= ~Q(status='completed')
            queryset = queryset.filter(q_objects)

        return queryset.annotate(
            has_pending=Exists(
                Transaction.objects.filter(
                    upload_file=OuterRef('pk'),
                    status__in=['pending', 'uncategorized'],
                    user=self.request.user,
                    transaction_type='expense'
                )
            )
        ).annotate(
            transactions_count=Count(
                'transactions',
                filter=Q(
                    transactions__transaction_type='expense',
                    transactions__user=self.request.user,
                )
            )
        )

    def _process_upload_file(self, uploaded_file) -> CsvProcessingResult:
        """
        Process file upload: parse, validate, and create transactions.
        Supports both CSV and Excel formats.

        Args:
            uploaded_file: Uploaded file (CSV or Excel)

        Returns:
            CsvProcessingResult with processing details
        """

        try:
            # Parse file using unified parser (handles both CSV and Excel)
            file_data = parse_uploaded_file(uploaded_file)

            if not file_data:
                return CsvProcessingResult(
                    upload_file=None,
                    rows_processed=0,
                    success=False,
                    error_message='Il file è vuoto.'
                )
            logging.info(f"File with {len(file_data)} rows parsed successfully.")
            # Create a preliminary UploadFile record for detection
            # We use the processor to detect the structure before persisting all transactions
            # This allows us to fail early if mandatory columns are missing
            upload_file_obj = UploadFile.objects.create(
                user=self.request.user,
                file_name=uploaded_file.name,
            )

            upload_file_obj = CsvStructureDetector().setup_upload_file_structure(file_data, upload_file_obj,
                                                                                 self.request.user)

            # Validate mandatory columns
            if not (upload_file_obj.date_column_name and
                    upload_file_obj.description_column_name and
                    (upload_file_obj.income_amount_column_name or upload_file_obj.expense_amount_column_name)):

                missing = []
                if not upload_file_obj.date_column_name: missing.append('data')
                if not upload_file_obj.description_column_name: missing.append('descrizione')
                if not (upload_file_obj.income_amount_column_name or upload_file_obj.expense_amount_column_name):
                    missing.append('importo (entrata o uscita)')

                error_msg = f"Struttura del file non riconosciuta. Colonne obbligatorie mancanti: {', '.join(missing)}."
                upload_file_obj.delete()

                return CsvProcessingResult(
                    upload_file=None,
                    rows_processed=0,
                    success=False,
                    error_message=error_msg
                )

            with transaction.atomic():
                upload_file = persist_uploaded_file(file_data, self.request.user, uploaded_file, upload_file_obj)

            if not upload_file:
                raise Exception("Failed to persist CSV upload record.")

            return CsvProcessingResult(
                upload_file=upload_file,
                rows_processed=len(file_data),
                success=True
            )

        except FileParserError as e:
            return CsvProcessingResult(
                upload_file=None,
                rows_processed=0,
                success=False,
                error_message=str(e)
            )
        except Exception as e:
            return CsvProcessingResult(
                upload_file=None,
                rows_processed=0,
                success=False,
                error_message=f'Errore durante l\'elaborazione del file: {str(e)}'
            )

    def get_context_data(self, **kwargs):
        """Add upload list, statistics, and form to context"""
        # Get context from both parent classes
        context = super().get_context_data(**kwargs)

        # Add upload form configuration
        context['upload_context'] = UploadContext(
            max_file_size_mb=10,
            allowed_formats=['CSV', 'XLSX', 'XLS']
        )

        # The queryset in context (recent_uploads) is already paginated and annotated via get_queryset
        context['uploads'] = context[self.context_object_name]

        # Use the unpaginated queryset for summary statistics
        full_queryset = self.get_queryset()

        # Add statistics
        total_uploads = full_queryset.count()
        total_size = full_queryset.aggregate(total=Sum('dimension'))['total'] or 0

        # total_transactions should be on the full queryset of current user expenses
        total_transactions = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense',
            upload_file__in=full_queryset
        ).count()

        context['statistics'] = UploadStatistics(
            total_uploads=total_uploads,
            total_size_bytes=total_size,
            total_size_mb=round(total_size / (1024 * 1024), 2),
            total_transactions=total_transactions,
        )
        context['has_pending'] = full_queryset.filter(has_pending=True).exists()
        context['selected_status'] = self.request.GET.getlist('status')
        categories_exist = Category.objects.filter(user=self.request.user).exists()
        if not categories_exist:
            default_categories = list(DefaultCategory.objects.values_list('name', flat=True))
            context['default_categories'] = default_categories

        return context

    def post(self, request, *args, **kwargs):
        """Handle POST requests (form submission)"""
        form = self.get_form()
        upload_file_query = UploadFile.objects.filter(
            user=self.request.user, status__in=['pending', 'processing']
        )
        if upload_file_query.exists():
            return self.form_invalid(form, upload_file_query)
        elif form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        """Process valid form submission"""
        csv_file = form.cleaned_data['file']

        # Process the CSV upload
        result = self._process_upload_file(csv_file)
        if result.success:
            upload_file = result.upload_file
            logging.info(f"Scheduling task for upload {upload_file.pk} of user {self.request.user.username}.")
            process_upload.delay(self.request.user.pk, upload_file.pk)

            if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'upload_id': upload_file.pk})

            messages.success(
                self.request,
                f'File caricato con successo! {result.rows_processed}'
            )
            # Advance onboarding if before step 3
            profile = self.request.user.profile
            if profile and profile.onboarding_step < 3:
                profile.onboarding_step = 3
                profile.show_no_category_modal = False
                profile.save()

        else:
            messages.error(self.request, result.error_message)
            return self.form_invalid(form)

        return super(FormView, self).form_valid(form)

    def form_invalid(self, form: UploadFileForm, uncompleted_query_set: QuerySet[UploadFile, UploadFile] | None = None):
        """Handle invalid form submission"""
        if uncompleted_query_set:
            messages.error(self.request,
                           "Ci sono ancora caricamenti in corso, cancellali oppure finisci di categorizzare le spese nella sezione Spese.")
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, error)

        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            all_errors = []
            storage = messages.get_messages(self.request)
            for message in storage:
                all_errors.append(str(message))

            if not all_errors:
                for field, errors in form.errors.items():
                    for error in errors:
                        all_errors.append(str(error))

            return JsonResponse({'error': " ".join(all_errors)}, status=400)

        # Need to manually get the list context for rendering
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))
