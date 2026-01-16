import csv
import io
import os
import threading
import time
from dataclasses import dataclass
from math import ceil
from typing import List, Dict

from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.postgres.aggregates import StringAgg
from django.core.exceptions import BadRequest, PermissionDenied
from django.core.paginator import Paginator
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Sum, Count, Case, When, Value, CharField, Exists, OuterRef, Q, Max, IntegerField
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, ListView, DeleteView, DetailView

from api.models import UploadFile, Transaction, Merchant, DefaultCategory
from api.models import Rule, Category
from api.views.rule_view import create_rule
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
    paginate_by = 10

    # FormView attributes
    form_class = UploadFileForm
    success_url = reverse_lazy('transactions_upload')

    # Shared attributes
    template_name = 'transactions/transactions_upload.html'

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
        status_filter = self.request.GET.get('status')
        if status_filter == 'ready':
            queryset = queryset.filter(status='completed')
        elif status_filter == 'not_ready':
            queryset = queryset.exclude(status='completed')

        return queryset

    def _get_user_rules(self) -> List[str]:
        """Get active user rules"""
        return list(
            Rule.objects.filter(
                user=self.request.user,
                is_active=True
            ).values_list('text_content', flat=True)
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
        upload_file_query = UploadFile.objects.filter(
            user=self.request.user,
            status__in=['pending', 'processing']
        ).distinct()

        if upload_file_query.exists():
            return CsvProcessingResult(
                upload_file=None,
                rows_processed=0,
                success=False,
                error_message='There is already a pending upload'
            )

        try:
            # Parse file using unified parser (handles both CSV and Excel)
            file_data = parse_uploaded_file(uploaded_file)

            if not file_data:
                return CsvProcessingResult(
                    upload_file=None,
                    rows_processed=0,
                    success=False,
                    error_message='The file is empty.'
                )

            with transaction.atomic():
                upload_file = persist_uploaded_file(file_data, self.request.user, uploaded_file)

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

        # Convert uploads to display dataclass
        uploads_list = context.get(self.context_object_name, [])
        queryset = self.get_queryset().annotate(
            has_pending=Exists(
                Transaction.objects.filter(
                    upload_file=OuterRef('pk'),
                    status__in=['pending','uncategorized'],
                    user=self.request.user,
                    transaction_type='expense'
                )
            )
        ).annotate(
            transactions_count=Count('transactions')
        )

        context['uploads'] = queryset

        # Add statistics
        total_uploads = queryset.count()
        total_size = queryset.aggregate(total=Sum('dimension'))['total'] or 0
        total_transactions = sum(
            upload.transactions.count() for upload in uploads_list
        )

        context['statistics'] = UploadStatistics(
            total_uploads=total_uploads,
            total_size_bytes=total_size,
            total_size_mb=round(total_size / (1024 * 1024), 2),
            total_transactions=total_transactions,
        )
        context['has_pending'] = queryset.filter(has_pending=True).exists()

        return context

    def post(self, request, *args, **kwargs):
        """Handle POST requests (form submission)"""
        form = self.get_form()
        if form.is_valid():
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
        else:
            messages.error(self.request, result.error_message)
            return self.form_invalid(form)

        return super(FormView, self).form_valid(form)

    def form_invalid(self, form):
        """Handle invalid form submission"""
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, error)

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
                user=self.request.user,
                is_active=True
            ).values_list('text_content', flat=True)
        )
        user_categories = Category.objects.filter(user=self.request.user)
        if not user_categories.exists():
            for default_category in DefaultCategory.objects.all():
                category = Category(user=user, name=default_category.name, description=default_category.description, is_default=True)
                category.save()

        # Process transactions using ExpenseUploadProcessor
        processor = ExpenseUploadProcessor(
            user=self.request.user,
            user_rules=user_rules,
            available_categories=list(
                Category.objects.filter(user=self.request.user)
            )
        )


        upload_file = processor.process_transactions(list(transactions), upload_file)

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


class UploadFileCleanView(DetailView):
    model = UploadFile
    template_name = 'transactions/upload_file_clean.html'
    context_object_name = 'upload_file'

    # Variabile di classe per controllare il numero di elementi per pagina
    paginate_by_merchant = 10

    def get_queryset(self):
        return UploadFile.objects.filter(user=self.request.user)

    def post(self, request, *args, **kwargs):
        csv_file = self.get_object()
        merchant_id = request.POST.get('merchant_id')
        new_category_id = request.POST.get('new_category_id')

        if not merchant_id or not new_category_id:
            raise BadRequest("Merchant ID and Category ID are required.")

        merchant = get_object_or_404(Merchant, id=merchant_id, user=self.request.user)
        new_category = get_object_or_404(Category, id=new_category_id, user=self.request.user)

        Transaction.objects.filter(
            upload_file=csv_file,
            merchant=merchant,
        ).update(category=new_category, status='categorized', modified_by_user=True)

        create_rule(merchant, new_category, self.request.user)

        # Redirect alla stessa pagina mantenendo eventuali parametri GET (come la pagina corrente)
        return redirect(request.META.get('HTTP_REFERER', 'transactions_upload_detail'))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        csv_file = self.object

        # 1. Base Queryset
        transactions_qs = csv_file.transactions.all().filter(
            transaction_type='expense'
        )

        # 2. Filtri
        search_query = self.request.GET.get('search', '')
        if search_query:
            transactions_qs = transactions_qs.filter(
                Q(description__icontains=search_query) |
                Q(merchant__name__icontains=search_query)
            )

        # 3. Aggregazione (Merchant Summary)
        merchant_group = transactions_qs.values(
            'merchant__id',
            'merchant__name'
        ).annotate(
            number_of_transactions=Count('id'),
            total_spent=Sum('amount'),
            # Use Max to find if any 'uncategorized' exists (1 = True, 0 = False)
            is_uncategorized=Max(
                Case(
                    When(status='uncategorized', then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            categories_list=StringAgg('category__name', delimiter=', ', distinct=True)
        ).order_by('-is_uncategorized', '-number_of_transactions', 'merchant__name')

        uncategorized_merchants = merchant_group.filter(is_uncategorized=1)
        categorized_merchants = merchant_group.filter(is_uncategorized=0)

        # 4. Paginazione del Merchant Summary
        paginator = Paginator(categorized_merchants, self.paginate_by_merchant)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # 5. Context
        context['uncategorized_merchants'] = uncategorized_merchants
        context['merchant_summary'] = page_obj  # Ora è un oggetto Page
        context['search_query'] = search_query
        context['categories'] = Category.objects.filter(user=self.request.user)
        return context