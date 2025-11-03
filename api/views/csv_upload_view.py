import csv
import io
import time
from dataclasses import dataclass
from typing import List, Dict

from django import forms
from django.contrib import messages
from django.core.validators import FileExtensionValidator
from django.db.models import Sum, Count, Case, When, Q, Value, CharField, Exists, OuterRef
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, DeleteView

from api.models import CsvUpload, Transaction
from api.models import Rule, Category
from processors.expense_upload_processor import ExpenseUploadProcessor


# --- Data Classes ---

@dataclass
class CsvProcessingResult:
    """Result of CSV processing operation"""
    csv_upload: CsvUpload | None
    rows_processed: int
    processing_time: int
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

class CsvUploadDelete(DeleteView):
    model = CsvUpload
    success_url = reverse_lazy('transactions_upload')

class CsvUploadForm(forms.Form):
    """Form for CSV file upload with validation"""

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

    file = forms.FileField(
        label='CSV File',
        help_text='Upload a CSV file (max 10MB)',
        widget=forms.FileInput(attrs={
            'accept': '.csv',
            'class': 'form-control'
        }),
        validators=[
            FileExtensionValidator(allowed_extensions=['csv'])
        ]
    )

    def clean_file(self):
        """Validate uploaded file"""
        file = self.cleaned_data.get('file')

        if not file:
            return file

        # Check file extension
        if not file.name.endswith('.csv'):
            raise forms.ValidationError('File must be a CSV file.')

        # Check file size
        if file.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError(
                f'File size must not exceed {self.MAX_FILE_SIZE / (1024 * 1024):.0f}MB.'
            )

        # Validate CSV structure
        try:
            file.seek(0)
            content = file.read().decode('utf-8-sig')
            csv_reader = csv.DictReader(io.StringIO(content))

            # Validate that file has content
            rows = list(csv_reader)
            if len(rows) == 0:
                raise forms.ValidationError('CSV file is empty.')

            file.seek(0)  # Reset file pointer

        except UnicodeDecodeError:
            raise forms.ValidationError('File encoding error. Please ensure the file is UTF-8 encoded.')
        except csv.Error as e:
            raise forms.ValidationError(f'Invalid CSV format: {str(e)}')
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


class CsvUploadView(ListView, FormView):
    """
    Combined view for CSV file upload and display of upload history.

    Responsibilities:
    - Display upload form with configuration context
    - Validate and process uploaded CSV files
    - Display paginated list of user's uploads
    - Show upload statistics
    """
    # ListView attributes
    model = CsvUpload
    context_object_name = 'recent_uploads'
    paginate_by = 10

    # FormView attributes
    form_class = CsvUploadForm
    success_url = reverse_lazy('transactions_upload')

    # Shared attributes
    template_name = 'transactions/transactions_upload.html'

    # Default categories to create for new users
    DEFAULT_CATEGORIES = [
        "Casa", "Spesa", "Auto", "Carburante", "Vita sociale", "Pizza",
        "Regali", "Vacanze", "Sport", "Bollette", "Scuola", "Bambini",
        "Shopping", "Abbonamenti", "Affitto", "Baby-sitter", "Trasporti",
        "Spese mediche", "Partita Iva", "Bonifico"
    ]

    def get_queryset(self):
        """Get uploads for the current user (ListView method)"""
        return CsvUpload.objects.filter(
            user=self.request.user
        ).select_related('user').prefetch_related('transactions').order_by('-upload_date')

    def _ensure_user_categories(self) -> List[str]:
        """Ensure user has categories, create defaults if needed"""
        user_categories = list(
            Category.objects.filter(user=self.request.user).values_list('name', flat=True)
        )

        if not user_categories:
            # Create default categories for new user
            Category.objects.bulk_create([
                Category(name=default_category, user=self.request.user)
                for default_category in self.DEFAULT_CATEGORIES
            ])
            return self.DEFAULT_CATEGORIES

        return user_categories

    def _get_user_rules(self) -> List[str]:
        """Get active user rules"""
        return list(
            Rule.objects.filter(
                user=self.request.user,
                is_active=True
            ).values_list('text_content', flat=True)
        )

    def _process_csv_upload(self, csv_file) -> CsvProcessingResult:
        """
        Process CSV upload: parse, validate, and create transactions.

        Args:
            csv_file: Uploaded CSV file

        Returns:
            CsvProcessingResult with processing details
        """
        start_time = time.time()

        try:
            # Parse CSV file
            csv_data = _parse_csv(csv_file)

            if not csv_data:
                return CsvProcessingResult(
                    csv_upload=None,
                    rows_processed=0,
                    processing_time=0,
                    success=False,
                    error_message='The CSV file is empty.'
                )

            # Get user rules and categories
            user_rules = self._get_user_rules()
            available_categories = self._ensure_user_categories()

            # Process transactions using ExpenseUploadProcessor
            processor = ExpenseUploadProcessor(
                user=self.request.user,
                user_rules=user_rules,
                available_categories=available_categories
            )

            csv_upload = processor.process_transactions(csv_data)

            # Calculate processing time and update record
            processing_time = int((time.time() - start_time) * 1000)
            csv_upload.processing_time = processing_time
            csv_upload.dimension = csv_file.size
            csv_upload.save()

            return CsvProcessingResult(
                csv_upload=csv_upload,
                rows_processed=len(csv_data),
                processing_time=processing_time,
                success=True
            )

        except csv.Error as e:
            return CsvProcessingResult(
                csv_upload=None,
                rows_processed=0,
                processing_time=int((time.time() - start_time) * 1000),
                success=False,
                error_message=f'Error parsing CSV file: {str(e)}'
            )
        except Exception as e:
            return CsvProcessingResult(
                csv_upload=None,
                rows_processed=0,
                processing_time=int((time.time() - start_time) * 1000),
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
            allowed_formats=['CSV']
        )

        # Convert uploads to display dataclass
        uploads_list = context.get(self.context_object_name, [])
        queryset = self.get_queryset().annotate(
            has_pending=Exists(
                Transaction.objects.filter(
                    csv_upload=OuterRef('pk'),
                    status='pending'
                )
            )
        ).annotate(
            status=Case(
                When(has_pending=True, then=Value('pending')),
                default=Value('categorized'),
                output_field=CharField()
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
        result = self._process_csv_upload(csv_file)

        if result.success:
            messages.success(
                self.request,
                f'File caricato con successo! {result.rows_processed} transazioni elaborate in {result.processing_time}ms.'
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
