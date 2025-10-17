from django.views.generic import FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.conf import settings
from django import forms
import csv
import io
from typing import List, Dict

from api.processors import ExpenseUploadProcessor


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


def _parse_csv(csv_file) -> List[Dict[str, str]]:
    """Parse CSV file and return list of row dictionaries."""
    decoded_file = csv_file.read().decode('utf-8-sig')
    io_string = io.StringIO(decoded_file)
    reader = csv.DictReader(io_string)
    return list(reader)


def _prepare_transactions(csv_data: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Add transaction IDs to each row for agent processing."""
    transactions = []
    for idx, row in enumerate(csv_data):
        transaction = {
            'id': f'tx_{idx:03d}',
            **row
        }
        transactions.append(transaction)
    return transactions


class CSVUploadView(LoginRequiredMixin, FormView):
    """
    View for handling CSV file uploads for transaction processing.

    Workflow:
    1. Parse CSV file
    2. Add transaction IDs (tx_000, tx_001, etc.)
    3. Delegate processing to ExpenseUploadProcessor
    4. Show results to user
    """
    template_name = 'transactions/transactions_upload.html'
    form_class = CSVUploadForm
    success_url = reverse_lazy('transaction_list')

    def get_batch_size(self):
        """Get batch size from settings"""
        return getattr(settings, 'CSV_BATCH_SIZE', 15)

    def form_valid(self, form):
        """Process valid form submission"""
        csv_file = form.cleaned_data['csv_file']

        try:
            # Parse CSV
            csv_data = _parse_csv(csv_file)

            if not csv_data:
                messages.error(self.request, 'The CSV file is empty.')
                return self.form_invalid(form)

            # Prepare transactions with IDs
            transactions = _prepare_transactions(csv_data)

            # Get user rules
            # TODO: Fetch user rules from database
            user_rules = [
                "Every PayPal transaction with amounts 2.2, 69.0, or 10.0 MUST be categorized as 'trasporti' (transports).",
                "RETITALIA is a fuel distributor and MUST ALWAYS be categorized as 'carburante' (fuel)."
            ]

            # Process transactions using processor
            processor = ExpenseUploadProcessor(
                user=self.request.user,
                batch_size=self.get_batch_size(),
                user_rules=user_rules
            )

            result = processor.process_transactions(transactions)
            stats = result['statistics']

            # Show success message
            messages.success(
                self.request,
                f'Successfully processed and saved {stats["total_persisted"]} transactions!'
            )

            return super().form_valid(form)

        except csv.Error as e:
            messages.error(self.request, f'Error parsing CSV file: {str(e)}')
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f'Unexpected error: {str(e)}')
            return self.form_invalid(form)