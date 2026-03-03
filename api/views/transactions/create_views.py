from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import BadRequest
from django.db import transaction
from django.db.models import Min
from django.shortcuts import redirect, render, get_object_or_404
from django.views import View

from api.models import Transaction, Category, Merchant
from api.privacy_utils import generate_blind_index
from api.services import DataRefreshService


class TransactionCreateView(View):

    def get(self, request, *args, **kwargs):
        categories = Category.objects.filter(user=request.user)
        context = {'categories': categories}
        return render(request, 'transactions/transaction_create.html', context)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user
        amount = request.POST.get('amount')
        merchant_id = request.POST.get('merchant_id')
        merchant_name = request.POST.get('merchant_name', '').strip()
        transaction_date = request.POST.get('transaction_date', '')
        category_name = request.POST.get('category_name', '').strip()

        # 2. Handle Merchant
        if merchant_id:
            merchant = get_object_or_404(Merchant, id=merchant_id, user=user)
        elif merchant_name:
            merchant_hash = generate_blind_index(merchant_name)
            merchant = Merchant.objects.filter(name_hash=merchant_hash, user=user).first()
            if not merchant:
                merchant = Merchant.objects.create(name=merchant_name, user=user)
        else:
            raise BadRequest("Non è stato possibile trovare o creare il merchant")

        # 1. Handle Category
        if category_name:
            category, created = Category.objects.get_or_create(
                name=category_name,
                user=user,
                defaults={'is_default': False}
            )
        else:
            raise BadRequest("Non è stato possibile trovare o creare la categoria")

        # 3. Create Transaction
        new_transaction = Transaction.objects.create(
            user=user,
            amount=amount if amount else None,
            merchant=merchant,
            transaction_date=transaction_date if transaction_date else None,
            description=f"Operazione in data {transaction_date} di importo {amount} presso {merchant_name}",
            category=category,
            status='categorized',
            modified_by_user=True,
            upload_file=None,
            manual_insert=True
        )

        new_transaction.refresh_from_db()
        start_date = new_transaction.transaction_date

        apply_to_all = request.POST.get('apply_to_all') in ['on', 'true']
        if apply_to_all and merchant:
            affected_transactions = Transaction.objects.filter(
                user=user,
                merchant=merchant
            )
            # Find the earliest transaction date among all that will be updated
            aggregation = affected_transactions.aggregate(Min('transaction_date'))
            min_date = aggregation['transaction_date__min']
            if min_date and (not start_date or min_date < start_date):
                start_date = min_date

            count = affected_transactions.update(
                category=category,
                status='categorized',
                modified_by_user=True
            )

            if count > 1:
                messages.success(request,
                                 f"Spesa aggiunta e altre {count - 1} transazioni di '{merchant.name}' sono state aggiornate.")
            else:
                messages.success(request, "Spesa aggiunta con successo.")
        else:
            messages.success(request, "Spesa aggiunta con successo.")

        if start_date:
            DataRefreshService.trigger_recomputation(user, start_date)

        return redirect('transaction_detail', pk=new_transaction.pk)
