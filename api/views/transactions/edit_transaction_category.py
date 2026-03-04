from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.models import Transaction, Category
from api.services.data_refresh.data_refresh_service import DataRefreshService
from processors.similarity_matcher import update_merchant_ema

class EditTransactionCategory(View):

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        transaction_id = request.POST.get('transaction_id')
        category_id = request.POST.get('category_id')

        tx = get_object_or_404(Transaction, id=transaction_id, user=request.user)
        cat = get_object_or_404(Category, id=category_id, user=request.user)

        with transaction.atomic():
            tx.category = cat
            tx.status = 'categorized'
            tx.modified_by_user = True
            tx.save()

            if tx.merchant:
                update_merchant_ema(tx.merchant, cat)

        DataRefreshService.trigger_recomputation(request.user, tx.transaction_date)

        return JsonResponse({'status': 'success'})
