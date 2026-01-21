from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.models import Transaction, Merchant, UploadFile

class TransactionByUploadFileAndMerchant(View):
    def get(self, request: HttpRequest, **kwargs):
        merchant_id = request.GET.get('merchant_id', None)
        upload_file_id = request.GET.get('upload_file_id', None)

        transactions_qs = Transaction.objects.filter(user=request.user).order_by('-transaction_date')

        if upload_file_id and upload_file_id != 'None' and upload_file_id != 'undefined' and upload_file_id != '':
            upload_file = get_object_or_404(UploadFile, user=request.user, id=upload_file_id)
            transactions_qs = transactions_qs.filter(upload_file=upload_file)

        if not merchant_id or merchant_id.lower() == 'none':
            merchant = None
            transactions_qs = transactions_qs.filter(merchant__isnull=True)
        else:
            # Security: Ensure objects belong to the requesting user
            merchant = get_object_or_404(Merchant, user=request.user, id=merchant_id)
            # Filter transactions
            transactions_qs = transactions_qs.filter(merchant=merchant)

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
            'description',
            'transaction_type'
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
