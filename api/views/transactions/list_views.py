import datetime
from dataclasses import dataclass, asdict, field
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.aggregates import StringAgg
from django.core.exceptions import BadRequest
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Max, Case, When, Value, IntegerField
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView

from api.models import Transaction, Category, Rule, UploadFile, Merchant
from api.views.rule_view import create_rule
from api.views.transactions.transaction_mixins import TransactionFilterMixin


@dataclass
class TransactionListContextData:
    """Context data for transaction list view"""
    categories: list[dict[str, Any]]
    selected_categories: list[str]
    selected_status: str
    selected_upload_file: str
    search_query: str
    uncategorized_transaction: QuerySet[Transaction, Transaction]  # QuerySet
    total_count: int
    total_amount: float
    category_count: int
    rules: QuerySet[Rule, Rule]  # QuerySet
    selected_months: list[str] = field(default_factory=list)
    def to_context(self) -> dict[str, Any]:
        """Convert dataclass to context dictionary"""
        return asdict(self)

class TransactionListView(LoginRequiredMixin, ListView, TransactionFilterMixin):
    """Display list of transactions with filtering and pagination"""
    model = Transaction
    template_name = 'transactions/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 20

    def get_paginate_by(self, queryset):
        if self.request.GET.get('view_type') == 'merchant':
            return None
        return self.paginate_by

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['transactions/components/transaction_list_htmx.html']
        return [self.template_name]

    def post(self, request, *args, **kwargs):
        merchant_id = request.POST.get('merchant_id')
        new_category_id = request.POST.get('new_category_id')

        if not merchant_id or not new_category_id:
            raise BadRequest("Merchant ID and Category ID are required.")

        merchant = get_object_or_404(Merchant, id=merchant_id, user=self.request.user)
        new_category = get_object_or_404(Category, id=new_category_id, user=self.request.user)

        # Update all transactions of this merchant (possibly filtered by upload_file if present in GET or URL)
        transactions_to_update = Transaction.objects.filter(
            user=self.request.user,
            merchant=merchant,
        )
        
        upload_file_id = self.kwargs.get('upload_file_id') or self.request.GET.get('upload_file')
        if upload_file_id:
            transactions_to_update = transactions_to_update.filter(upload_file_id=upload_file_id)
            
        transactions_to_update.update(category=new_category, status='categorized', modified_by_user=True)

        create_rule(merchant, new_category, self.request.user)

        # Advance onboarding if at step 4
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.onboarding_step < 5:
            profile.onboarding_step = 5
            profile.save()

        return redirect(request.META.get('HTTP_REFERER', 'transaction_list'))

    def get_queryset(self):
        return self.get_transaction_filter_query()

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        filters = self.get_transaction_filters()
        view_type = filters['view_type']
        context['view_type'] = view_type

        # Use the unpaginated queryset for summary statistics
        user_transactions = self.object_list

        # Get all categories for filter dropdown
        categories = list(Category.objects.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        ).order_by('name').values('id', 'name'))

        uncategorized_transaction = Transaction.objects.filter(
            user=self.request.user,
            status='uncategorized',
            transaction_type='expense'
        ).select_related('upload_file')

        upload_file_id = filters['upload_file_id']
        if upload_file_id:
            uncategorized_transaction = uncategorized_transaction.filter(upload_file_id=upload_file_id)
            context['upload_file'] = get_object_or_404(UploadFile, id=upload_file_id, user=self.request.user)


        transaction_list_context = TransactionListContextData(
            categories=categories,
            selected_status=filters['status'],
            selected_upload_file=upload_file_id or '',
            search_query=filters['search'],
            uncategorized_transaction=uncategorized_transaction,
            total_count=self.get_queryset().count(),
            total_amount=self.get_queryset().aggregate(
                total=Sum('amount')
            )['total'] or 0,
            category_count=self.get_queryset().values('category').distinct().count(),
            rules=Rule.objects.filter(user=self.request.user, is_active=True),
            selected_categories=filters['category_ids'],
            selected_months=filters['months']
        )
        context.update(transaction_list_context.to_context())

        # Add amount filter context
        context['selected_amount'] = filters['amount'] or ''
        context['selected_amount_operator'] = filters['amount_operator']
        context['year'] = filters['year']
        context['selected_months'] = [str(m) for m in filters['months']]

        if view_type == 'merchant':
            # Aggregate transactions by merchant
            merchant_group = user_transactions.values(
                'merchant__id',
                'merchant__name'
            ).annotate(
                number_of_transactions=Count('id'),
                total_spent=Sum('amount'),
                is_uncategorized=Max(
                    Case(
                        When(status='uncategorized', then=Value(1)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                ),
                categories_list=StringAgg('category__name', delimiter=', ', distinct=True),
                category_id=Max('category__id')
            ).order_by('-is_uncategorized', '-number_of_transactions', 'merchant__name')

            context['uncategorized_merchants'] = merchant_group.filter(is_uncategorized=1)
            categorized_merchants = merchant_group.filter(is_uncategorized=0)

            # Paginate merchants
            paginator = Paginator(categorized_merchants, 10)
            page_number = self.request.GET.get('page')
            context['merchant_summary'] = paginator.get_page(page_number)

        return context