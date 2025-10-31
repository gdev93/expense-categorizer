import csv
import io
from typing import List, Dict

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import FormView

from api.models import Rule, Category, CsvUpload
from processors.expense_upload_processor import ExpenseUploadProcessor


class CSVUploadForm(forms.Form):
    """Form for CSV file upload"""
    csv_file = forms.FileField(
        label='Upload CSV File',
        help_text='Select a CSV file containing your transactions',
        widget=forms.FileInput(attrs={
            'accept': '.csv',
            'class': 'form-control'
        })
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data['csv_file']

        if not csv_file.name.endswith('.csv'):
            raise forms.ValidationError('File must be a CSV file.')

        if csv_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('File size must not exceed 10MB.')

        return csv_file


def _parse_csv(csv_file) -> List[Dict[str,str]]:
    """Parse CSV file and return list of row dictionaries."""
    decoded_file = csv_file.read().decode('utf-8-sig')
    io_string = io.StringIO(decoded_file)
    reader = csv.DictReader(io_string)
    return list(reader)


class CSVUploadView(LoginRequiredMixin,FormView):
    """
    View for handling CSV file uploads for transaction processing.

    Workflow:
    1. Parse CSV file
    2. Add transaction IDs (tx_000,tx_001,etc.)
    3. Delegate processing to ExpenseUploadProcessor
    4. Show results to user
    """
    template_name = 'transactions/transactions_upload.html'
    form_class = CSVUploadForm
    success_url = reverse_lazy('transaction_list')
    default_categories:list[str] = "Casa,Spesa,Auto,Carburante,Vita sociale,Pizza,Regali,Vacanze,Sport,Bollette,Scuola,Bambini,Shopping,Abbonamenti,Affitto,Baby-sitter,Trasporti,Spese mediche,Partita Iva, Bonifico".split(',')

    def form_valid(self,form):
        """Process valid form submission"""
        csv_file = form.cleaned_data['csv_file']

        try:
            # Parse CSV
            csv_data = _parse_csv(csv_file)

            if not csv_data:
                messages.error(self.request,'The CSV file is empty.')
                return self.form_invalid(form)


            # Get user rules
            user_rules = list(Rule.objects.filter(user=self.request.user,is_active=True).values_list('text_content',flat=True))
            user_categories = list(Category.objects.filter(user=self.request.user).values_list('name', flat=True))
            if not user_categories:
                Category.objects.bulk_create([
                    Category(name=default_category, user=self.request.user)
                    for default_category in self.default_categories
                ])
                available_categories = self.default_categories
            else:
                available_categories = user_categories
            processor = ExpenseUploadProcessor(
                user=self.request.user,
                user_rules=user_rules,
                available_categories=available_categories
            )

            processor.process_transactions(csv_data)

            # Show success message
            messages.success(
                self.request,
                f'Successfully processed!-'
            )

            return super().form_valid(form)

        except csv.Error as e:
            messages.error(self.request,f'Error parsing CSV file: {str(e)}')
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request,f'Unexpected error: {str(e)}')
            return self.form_invalid(form)