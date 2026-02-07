import csv
import io
import logging
import os
import threading
import time
from dataclasses import dataclass
from math import ceil
from typing import List, Dict

from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Sum, Count, Exists, OuterRef, Q, QuerySet
from django.http import HttpResponse, JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, ListView, DeleteView

from api.models import Rule, Category
from api.models import UploadFile, Transaction, Merchant, DefaultCategory
from processors.csv_structure_detector import CsvStructureDetector
from processors.expense_upload_processor import ExpenseUploadProcessor, persist_uploaded_file
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


def _parse_csv(csv_file) -> List[Dict[str, str]]:
    """Parse CSV file and return list of row dictionaries."""
    csv_file.seek(0)
    decoded_file = csv_file.read().decode('utf-8-sig')
    io_string = io.StringIO(decoded_file)
    reader = csv.DictReader(io_string)
    return list(reader)

class UploadFileDelete(DeleteView):
    model = UploadFile
    template_name = 'transactions/upload_file_confirm_delete.html'
    success_url = reverse_lazy('transactions_upload')

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def post(self, request, *args, **kwargs):
        messages.success(request, "Caricamento eliminato correttamente.")
        response = super().post(request, *args, **kwargs)
        # Delete merchants that have no transactions and no rules
        Merchant.objects.filter(user=request.user).exclude(
            transactions__isnull=False
        ).exclude(
            rule__isnull=False
        ).delete()
        return response


class UploadFileForm(forms.Form):
    """Form for CSV/Excel file upload with validation"""

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

    file = forms.FileField(
        label='Transaction File',
        help_text='Upload a CSV or Excel file (max 10MB)',
        widget=forms.FileInput(attrs={
            'accept': '.csv,.xlsx,.xls',
            'class': 'form-control'
        }),
        validators=[
            FileExtensionValidator(allowed_extensions=['csv', 'xlsx', 'xls'])
        ]
    )

    def clean_file(self):
        """Validate uploaded file"""
        file = self.cleaned_data.get('file')

        if not file:
            return file

        # Check file extension
        allowed_extensions = ('.csv', '.xlsx', '.xls')
        if not file.name.lower().endswith(allowed_extensions):
            raise forms.ValidationError('File must be a CSV or Excel file.')

        # Check file size
        if file.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError(
                f'File size must not exceed {self.MAX_FILE_SIZE / (1024 * 1024):.0f}MB.'
            )

        # Validate file content based on type
        try:
            # Validate that file has content
            if len(file) == 0:
                raise forms.ValidationError('File is empty.')

            file.seek(0)  # Reset file pointer

        except FileParserError as e:
            raise forms.ValidationError(str(e))
        except Exception as e:
            raise forms.ValidationError(f'Error reading file: {str(e)}')

        return file

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
        if self.request.headers.get('HX-Request'):
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
                    status__in=['pending','uncategorized'],
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

            # Create a preliminary UploadFile record for detection
            # We use the processor to detect the structure before persisting all transactions
            # This allows us to fail early if mandatory columns are missing
            upload_file_obj = UploadFile.objects.create(user=self.request.user, file_name=uploaded_file.name)
            upload_file_obj = CsvStructureDetector().setup_upload_file_structure(file_data, upload_file_obj, self.request.user)

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
            messages.success(
                self.request,
                f'File caricato con successo! {result.rows_processed}'
            )
            # Advance onboarding if before step 3
            profile = getattr(self.request.user, 'profile', None)
            if profile and profile.onboarding_step < 3:
                profile.onboarding_step = 3
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

            return JsonResponse({'error': " ".join(all_errors)}, status=400)

        # Need to manually get the list context for rendering
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form))


class UploadProgressView(View):
    long_polling_limit = os.getenv('LONG_POLLING_SLEEP', 5)

    def get(self, request, *args, **kwargs):
        upload_file_query = UploadFile.objects.filter(user=self.request.user, status='processing').distinct()
        if not upload_file_query.exists():
            return HttpResponse(status=404)
        upload_file = upload_file_query.first()
        time.sleep(self.long_polling_limit)
        total = Transaction.objects.filter(upload_file=upload_file, user=request.user).count()
        current_pending = Transaction.objects.filter(upload_file=upload_file, user=request.user, status='pending').count()
        if current_pending == 0:
            return JsonResponse(status=200, data={
                "total": total,
                "current_pending": 0,
                "current_categorized": total,
                "percentage": "100%"
            })
        current_categorized = Transaction.objects.filter(upload_file=upload_file, user=request.user,
                                                         status='categorized').count()
        return JsonResponse(status=200, data={
            "total": total,
            "current_pending": current_pending,
            "current_categorized": current_categorized,
            "percentage": f"{ceil(current_categorized / total * 100)}%"
        })

class UploadProcessView(View):

    def post(self, request, *args, **kwargs):
        upload_file_query = UploadFile.objects.filter(user=self.request.user, status='pending').distinct()
        if not upload_file_query.exists():
            logging.warning(f"No upload file found for processing for user {self.request.user.username}.")
            return HttpResponse(status=404)
        upload_file = upload_file_query.first()
        thread = threading.Thread(
            target=self._do_process,
            args=(request.user, upload_file,),
            daemon=True
        )
        thread.start()
        return HttpResponse(status=202)

    def _do_process(self, user: User, upload_file: UploadFile) -> HttpResponse:
        start_time = time.time()

        upload_file.status = 'processing'
        upload_file.save()

        transactions = Transaction.objects.filter(upload_file=upload_file, user=user, status='pending')
        user_rules = list(
            Rule.objects.filter(
                user=user,
                is_active=True
            ).values_list('text_content', flat=True)
        )
        user_categories = Category.objects.filter(user=user)
        if not user_categories.exists():
            for default_category in DefaultCategory.objects.all():
                category = Category(user=user, name=default_category.name, description=default_category.description, is_default=True)
                category.save()

        # Process transactions using ExpenseUploadProcessor
        processor = ExpenseUploadProcessor(
            user=user,
            user_rules=user_rules,
            available_categories=list(
                Category.objects.filter(user=user)
            )
        )

        logging.info(f"{user}'s data {upload_file.file_name} is being processed.")
        upload_file = processor.process_transactions(transactions.iterator(), upload_file)

        # Calculate processing time and update record
        processing_time = int((time.time() - start_time) * 1000)
        upload_file.processing_time = processing_time
        upload_file.save()
        return HttpResponse(status=201)

class UploadFileCheckView(View):

    def get(self, request, *args, **kwargs):
        upload_file_query = UploadFile.objects.filter(user=self.request.user, status='processing').distinct()
        if not upload_file_query.exists():
            return HttpResponse(status=404)
        upload_file = upload_file_query.first()
        return JsonResponse(status=200, data={
            "total": Transaction.objects.filter(upload_file=upload_file, user=request.user).count(),
            "current_pending": Transaction.objects.filter(upload_file=upload_file, user=request.user, status='pending').count(),
            "current_categorized": Transaction.objects.filter(upload_file=upload_file, user=request.user, status='categorized').count(),
        })



