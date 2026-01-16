import os
from calendar import monthrange
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView

from api.models import Transaction, Category, Merchant, UploadFile

pre_check_confidence_threshold = os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', 0.8)

class TransactionIncomeCreateView(LoginRequiredMixin, CreateView):
    """
    A view to create a new Transaction instance of type income.
    Simplified form with only date and amount required.
    """
    model = Transaction
    template_name = 'transactions/transaction_income.html'
    fields = [
        'transaction_date',
        'amount',
    ]

    @transaction.atomic
    def form_valid(self, form):
        """
        Set proper transaction defaults for income type.
        Income transactions don't require merchant or category.
        """
        # Set transaction defaults for income
        form.instance.user = self.request.user
        form.instance.transaction_type = 'income'
        form.instance.description = self.request.POST.get('description', 'User input')
        form.instance.modified_by_user = True
        form.instance.status = 'categorized'

        # Income transactions typically don't have a merchant
        form.instance.merchant = None
        form.instance.merchant_raw_name = 'Income'

        # Get the transaction date from the form
        transaction_date = form.cleaned_data.get('transaction_date')

        # Calculate the first and last day of the month
        first_day_of_month = transaction_date.replace(day=1)

        # Get the last day of the month using monthrange
        last_day = monthrange(transaction_date.year, transaction_date.month)[1]
        last_day_of_month = transaction_date.replace(day=last_day)

        # Find CSV upload that has transactions in this date range
        upload_file_in_date_range = UploadFile.objects.filter(
            user=self.request.user,
            transactions__transaction_date__gte=first_day_of_month,
            transactions__transaction_date__lte=last_day_of_month
        ).distinct().first()

        # Associate the transaction with the found CSV upload (if any)
        form.instance.upload_file = upload_file_in_date_range

        self.object = form.save()

        # Redirect to transaction list after successful creation
        return redirect(self.request.POST.get("redirect_target_url") or 'transaction_list')

    def get_success_url(self):
        """Redirect to transaction list after successful creation"""
        return reverse('transaction_list')

class TransactionCreateView(LoginRequiredMixin, CreateView):
    """
    A view to create a new Transaction instance of type expense.
    Handles all transaction data including merchant, category, and amount.
    """
    model = Transaction
    template_name = 'transactions/transaction_expense_create.html'
    fields = [
        'transaction_date',
        'amount',
        'merchant_raw_name',
        'description',
        'category'
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(
            Q(user=self.request.user) | Q(is_default=True)
        ).distinct()
        return context

    @transaction.atomic
    def form_valid(self, form):
        """
        Customizes form validation to handle new category creation,
        merchant assignment, and set proper transaction defaults.
        """
        # Handle new category creation
        new_category_name = self.request.POST.get('new_category_name', '').strip()

        if new_category_name:
            new_category, created = Category.objects.get_or_create(
                name=new_category_name,
                user=self.request.user,
                defaults={'is_default': False}
            )
            form.instance.category = new_category

        # Handle merchant
        merchant_name = self.request.POST.get('merchant_raw_name', '').strip()

        if merchant_name:
            merchant_db = Merchant.get_similar_merchants_by_names(merchant_name, self.request.user, pre_check_confidence_threshold).first()
            if not merchant_db:
                merchant_db = Merchant.objects.create(name=merchant_name, user=self.request.user)
            form.instance.merchant = merchant_db

        # Set transaction defaults
        form.instance.user = self.request.user
        form.instance.transaction_type = 'expense'
        form.instance.modified_by_user = True
        form.instance.status = 'categorized'

        self.object = form.save()

        # Redirect to transaction list after successful creation
        return redirect('transaction_list')

    def get_success_url(self):
        """Redirect to transaction list after successful creation"""
        return reverse('transaction_list')
