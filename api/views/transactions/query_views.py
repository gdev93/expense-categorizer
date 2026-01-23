from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.models import Merchant, UploadFile
from api.views.transactions.transaction_mixins import TransactionFilterMixin


class TransactionByMerchant(TransactionFilterMixin, View):
    def get(self, request: HttpRequest, **kwargs):
        merchant_id = request.GET.get('merchant_id', None)

        transactions_qs = self.get_transaction_filter_query()

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
