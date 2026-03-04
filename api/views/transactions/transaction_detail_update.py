import os
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Min
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import UpdateView

from api.models import Transaction, Category, Merchant
from api.forms import TransactionForm
from api.privacy_utils import generate_blind_index
from api.services.data_refresh.data_refresh_service import DataRefreshService

pre_check_confidence_threshold = os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', 0.8)

class TransactionDetailUpdateView(UpdateView):
    """
    A view to display and handle updates for a single Transaction instance.
    The view will re-render the detail template upon successful update,
    staying on the current page.
    """
    model = Transaction
    form_class = TransactionForm
    template_name = 'transactions/transaction_detail.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        """Handle both updates and deletes"""
        if 'delete' in request.POST:
            return self.delete(request, *args, **kwargs)
        return super().post(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Handle transaction deletion"""
        obj = self.get_object()
        date = obj.transaction_date
        obj.delete()
        if date:
            DataRefreshService.trigger_recomputation(request.user, date)

        messages.success(request, "Spesa eliminata con successo.")

        # Check if filters were stored before deletion
        redirect_filters = request.POST.get('redirect_filters', '')

        # Build redirect URL with preserved filters
        redirect_url = reverse('transaction_list')

        if redirect_filters:
            # The filters already include the '?' or are empty
            redirect_url = redirect_url + redirect_filters

        return redirect(redirect_url)

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(
            Q(user=self.request.user)
        ).distinct()
        context["is_update"] = True
        return context

    @transaction.atomic
    def form_valid(self, form):
        """
        Customizes form validation to handle new category creation,
        set the modified_by_user flag, and most importantly,
        **return the rendered template instead of a redirect.**
        """
        category_name = self.request.POST.get('category_name', '').strip()
        new_category = None

        if category_name:
            new_category, created = Category.objects.get_or_create(
                name=category_name,
                user=self.request.user,  # Assigns the new category to the current user
                defaults={'is_default': False}
            )

        merchant_name = self.request.POST.get('merchant_name', '').strip()
        if merchant_name:
            merchant_hash = generate_blind_index(merchant_name)
            merchant_db = Merchant.objects.filter(name_hash=merchant_hash, user=self.request.user).first()
            if not merchant_db:
                merchant_db = Merchant.objects.create(name=merchant_name, user=self.request.user)
            form.instance.merchant = merchant_db

        form.instance.category = new_category
        form.instance.modified_by_user = True
        form.instance.status = 'categorized'
        
        old_date = self.object.transaction_date
        old_amount = self.object.amount
        self.object = form.save()
        new_date = self.object.transaction_date

        start_date = None
        if old_date and new_date:
            start_date = min(old_date, new_date)
        elif old_date:
            start_date = old_date
        elif new_date:
            start_date = new_date

        apply_to_all = self.request.POST.get('apply_to_all') in ['on', 'true']
        if apply_to_all and self.object.merchant:
            affected_transactions = Transaction.objects.filter(
                user=self.request.user,
                merchant=self.object.merchant
            )
            # Find the earliest transaction date among all that will be updated
            aggregation = affected_transactions.aggregate(Min('transaction_date'))
            min_date = aggregation['transaction_date__min']
            if min_date and (not start_date or min_date < start_date):
                start_date = min_date

            count = affected_transactions.update(
                category=self.object.category,
                status='categorized',
                modified_by_user=True
            )
            messages.success(self.request,
                             f"Transazione salvata e altre {count - 1} transazioni di '{self.object.merchant.name}' sono state aggiornate.")
        else:
            messages.success(self.request, "Transazione salvata con successo.")

        if start_date:
            DataRefreshService.trigger_recomputation(self.request.user, start_date)

        # Instead of redirecting, render the detail template directly
        return self.render_to_response(self.get_context_data(form=form))

    def form_invalid(self, form):
        messages.error(self.request, "Errore durante il salvataggio della transazione.")
        return self.render_to_response(self.get_context_data(form=form))
