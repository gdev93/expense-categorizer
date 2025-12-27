from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.models import Transaction, Merchant, CsvUpload

class TransactionByCsvUploadAndMerchant(View):
    def get(self, request: HttpRequest, **kwargs):
        merchant_id = request.GET.get('merchant_id', None)
        csv_upload_id = request.GET.get('csv_upload_id', None)
        csv_upload = get_object_or_404(CsvUpload, user=request.user, id=csv_upload_id)
        if not merchant_id or merchant_id.lower() == 'none':
            merchant = None
            transactions_qs = Transaction.objects.filter(user=request.user, csv_upload=csv_upload, merchant__isnull=True).order_by('-transaction_date')
        else:
            # Security: Ensure objects belong to the requesting user
            merchant = get_object_or_404(Merchant, user=request.user, id=merchant_id)
            # Filter transactions
            transactions_qs = Transaction.objects.filter(
                merchant=merchant,
                csv_upload=csv_upload,
                user=request.user
            ).order_by('-transaction_date')

        # Get date range for the UI
        first_date = None
        last_date = None
        if transactions_qs.exists():
            first_date = transactions_qs.last().transaction_date
            last_date = transactions_qs.first().transaction_date

        # Convert QuerySet to list of dicts for JSON serialization
        # Add or remove fields here based on what you want to show in the UI
        transactions_data = list(transactions_qs.values(
            'id',
            'transaction_date',
            'amount',
            'description'
        ))

        return JsonResponse(
            data={
                'transactions': transactions_data,
                'first_date': first_date,
                'last_date': last_date,
                'merchant_name': merchant.name if merchant else None
            },
            safe=False
        )
