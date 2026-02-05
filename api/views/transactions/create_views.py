from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView

from api.models import Transaction, Category, Merchant

class TransactionCreateView(LoginRequiredMixin, CreateView):
    model = Transaction
    template_name = 'transactions/transaction_create.html'
    fields = [
        'transaction_date',
        'amount',
        'merchant_raw_name',
        'description',
        'category'
    ]

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['transactions/components/transaction_create_form.html']
        return [self.template_name]

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.filter(
            Q(user=self.request.user)
        ).distinct()
        return context

    @transaction.atomic
    def form_valid(self, form):
        form.instance.user = self.request.user
        
        new_category_name = self.request.POST.get('new_category_name', '').strip()
        if new_category_name:
            new_category, created = Category.objects.get_or_create(
                name=new_category_name,
                user=self.request.user,
                defaults={'is_default': False}
            )
        else:
            new_category = form.cleaned_data.get('category')

        merchant_name = self.request.POST.get('merchant_raw_name', '').strip()
        if merchant_name:
            merchant_db = Merchant.objects.filter(name=merchant_name, user=self.request.user).first()
            if not merchant_db:
                merchant_db = Merchant.objects.create(name=merchant_name, user=self.request.user)
            form.instance.merchant = merchant_db

        form.instance.category = new_category
        form.instance.modified_by_user = True
        form.instance.status = 'categorized'
        
        self.object = form.save()
        messages.success(self.request, "Spesa aggiunta con successo.")
        
        return redirect(reverse('transaction_list'))
