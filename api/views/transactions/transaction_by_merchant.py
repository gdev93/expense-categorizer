from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
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

        if request.headers.get('HX-Request'):
            return render(
                request,
                'transactions/components/merchant_transactions.html',
                {
                    'transactions': transactions_qs,
                    'merchant': merchant
                }
            )

        # Convert QuerySet to list of dicts for JSON serialization
        # We manually build the list to include decrypted amount and description properties
        transactions_data = []
        for t in transactions_qs:
            transactions_data.append({
                'id': t.id,
                'transaction_date': t.transaction_date,
                'amount': t.amount,
                'description': t.description,
                'transaction_type': t.transaction_type
            })

        return JsonResponse(
            data={
                'transactions': transactions_data,
                'first_date': first_date,
                'last_date': last_date,
                'merchant_name': merchant.name if merchant else None
            },
            safe=False
        )
