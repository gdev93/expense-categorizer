from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect, render, get_object_or_404
from django.views import View

from api.models import Transaction, Category, Merchant


class TransactionCreateView(LoginRequiredMixin, View):

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
        description = request.POST.get('description', '')
        category_name = request.POST.get('category_name', '').strip()

        # 1. Handle Category
        if category_name:
            category, created = Category.objects.get_or_create(
                name=category_name,
                user=user,
                defaults={'is_default': False}
            )
        else:
            category = None

        # 2. Handle Merchant
        if merchant_id:
            merchant = get_object_or_404(Merchant, id=merchant_id, user=user)
        elif merchant_name:
            merchant = Merchant.objects.filter(name=merchant_name, user=user).first()
            if not merchant:
                merchant = Merchant.objects.create(name=merchant_name, user=user)
        else:
            merchant = None

        # 3. Create Transaction
        new_transaction = Transaction.objects.create(
            user=user,
            amount=amount if amount else None,
            merchant=merchant,
            merchant_raw_name=merchant_name,
            transaction_date=transaction_date if transaction_date else None,
            description=description,
            category=category,
            status='categorized',
            modified_by_user=True,
            upload_file=None
        )

        messages.success(request, "Spesa aggiunta con successo.")

        apply_to_all = request.POST.get('apply_to_all') in ['on', 'true']
        if apply_to_all and merchant:
            Transaction.objects.filter(
                user=user,
                merchant=merchant
            ).update(
                category=category,
                status='categorized',
                modified_by_user=True
            )

        return redirect('transaction_detail', pk=new_transaction.pk)
