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


@dataclass
class TransactionListContextData:
    """Context data for transaction list view"""
    categories: list[dict[str, Any]]
    selected_category: str
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

class TransactionListView(LoginRequiredMixin, ListView):
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

    def _get_selected_year(self, queryset):
        get_year = self.request.GET.get('year')
        if get_year:
            try:
                return int(get_year)
            except (TypeError, ValueError):
                raise BadRequest("Invalid year format.")
        else:
            # Fallback to most recent transaction year if no year provided
            first_t = queryset.first()
            return first_t.transaction_date.year if first_t else datetime.datetime.now().year

    def get_queryset(self):
        """Filter transactions based on user and query parameters"""
        # Advance onboarding if before step 5 and filters are used
        profile = getattr(self.request.user, 'profile', None)
        if profile and profile.onboarding_step < 4:
            filter_params = ['category', 'upload_file', 'amount', 'search', 'months', 'month', 'year']
            if any(self.request.GET.get(param) for param in filter_params):
                profile.onboarding_step = 4
                profile.save()

        queryset = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense',
        ).select_related('category', 'merchant', 'upload_file').order_by('-transaction_date', '-created_at')

        # Filter by category
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # Filter by upload_file (from URL or GET)
        upload_file_id = self.kwargs.get('upload_file_id') or self.request.GET.get('upload_file')
        if upload_file_id:
            queryset = queryset.filter(upload_file_id=upload_file_id)

        # Filter by amount
        amount = self.request.GET.get('amount')
        amount_operator = self.request.GET.get('amount_operator', 'eq')
        if amount:
            try:
                amount_value = float(amount)
                if amount_operator == 'eq':
                    queryset = queryset.filter(amount=amount_value)
                elif amount_operator == 'gt':
                    queryset = queryset.filter(amount__gt=amount_value)
                elif amount_operator == 'gte':
                    queryset = queryset.filter(amount__gte=amount_value)
                elif amount_operator == 'lt':
                    queryset = queryset.filter(amount__lt=amount_value)
                elif amount_operator == 'lte':
                    queryset = queryset.filter(amount__lte=amount_value)
            except (ValueError, TypeError):
                raise BadRequest("Invalid amount format.")

        # Search filter
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(merchant__name__icontains=search_query) |
                Q(merchant_raw_name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # Year logic
        selected_year = self._get_selected_year(queryset)
        if not upload_file_id:
            queryset = queryset.filter(transaction_date__year=selected_year)

        # Filter by months
        selected_months = self.request.GET.getlist('months')
        single_month = self.request.GET.get('month')
        if single_month and single_month not in selected_months:
            selected_months.append(single_month)

        if selected_months:
            month_queries = Q()
            for month_str in selected_months:
                try:
                    month = int(month_str)
                    month_queries |= Q(transaction_date__month=month)
                except (ValueError, TypeError):
                    pass
            if month_queries:
                queryset = queryset.filter(month_queries)

        # For the main list view, we only want categorized transactions
        # to avoid duplication with the uncategorized section in the template.
        if self.request.GET.get('view_type', 'list') == 'list':
            return queryset.filter(category__isnull=False, merchant_id__isnull=False)

        return queryset

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        view_type = self.request.GET.get('view_type', 'list')
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

        upload_file_id = self.kwargs.get('upload_file_id') or self.request.GET.get('upload_file', '')
        if upload_file_id:
            uncategorized_transaction = uncategorized_transaction.filter(upload_file_id=upload_file_id)
            context['upload_file'] = get_object_or_404(UploadFile, id=upload_file_id, user=self.request.user)


        transaction_list_context = TransactionListContextData(
            categories=categories,
            selected_status=self.request.GET.get('status', ''),
            selected_upload_file=upload_file_id,
            search_query=self.request.GET.get('search', ''),
            uncategorized_transaction=uncategorized_transaction,
            total_count=self.get_queryset().count(),
            total_amount=self.get_queryset().aggregate(
                total=Sum('amount')
            )['total'] or 0,
            category_count=self.get_queryset().values('category').distinct().count(),
            rules=Rule.objects.filter(user=self.request.user, is_active=True),
            selected_category=self.request.GET.get('category', ''),
            selected_months=self.request.GET.getlist('months')
        )
        context.update(transaction_list_context.to_context())

        # Add amount filter context
        context['selected_amount'] = self.request.GET.get('amount', '')
        context['selected_amount_operator'] = self.request.GET.get('amount_operator', 'eq')
        context['year'] = self._get_selected_year(user_transactions)

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

class IncomeListView(LoginRequiredMixin, ListView):
    """Display list of income transactions with filtering and pagination"""
    model = Transaction
    template_name = 'transactions/transaction_income_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

    def _get_selected_year(self, queryset):
        get_year = self.request.GET.get('year')
        if get_year:
            try:
                return int(get_year)
            except (TypeError, ValueError):
                raise BadRequest("Invalid year format.")
        else:
            # Fallback to most recent transaction year if no year provided
            first_t = queryset.first()
            return first_t.transaction_date.year if first_t else datetime.datetime.now().year

    def get_queryset(self):
        queryset = (Transaction.objects
                    .filter(
                        user=self.request.user,
                        transaction_type='income'
        ).order_by('-transaction_date', '-created_at'))

        # Filter by amount
        amount = self.request.GET.get('amount')
        amount_operator = self.request.GET.get('amount_operator', 'eq')
        if amount:
            try:
                amount_value = float(amount)
                if amount_operator == 'eq':
                    queryset = queryset.filter(amount=amount_value)
                elif amount_operator == 'gt':
                    queryset = queryset.filter(amount__gt=amount_value)
                elif amount_operator == 'gte':
                    queryset = queryset.filter(amount__gte=amount_value)
                elif amount_operator == 'lt':
                    queryset = queryset.filter(amount__lt=amount_value)
                elif amount_operator == 'lte':
                    queryset = queryset.filter(amount__lte=amount_value)
            except (ValueError, TypeError):
                raise BadRequest("Invalid amount format.")

        # Year logic
        selected_year = self._get_selected_year(queryset)
        queryset = queryset.filter(transaction_date__year=selected_year)

        # Filter by months
        selected_months = self.request.GET.getlist('months')
        single_month = self.request.GET.get('month')
        if single_month and single_month not in selected_months:
            selected_months.append(single_month)

        if selected_months:
            month_queries = Q()
            for month_str in selected_months:
                try:
                    month = int(month_str)
                    month_queries |= Q(transaction_date__month=month)
                except (ValueError, TypeError):
                    pass
            if month_queries:
                queryset = queryset.filter(month_queries)

        # Search filter
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(Q(description__icontains=search_query))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_transactions = self.object_list

        context.update({
            'total_count': user_transactions.count(),
            'total_amount': user_transactions.filter(status="categorized").aggregate(total=Sum('amount'))['total'] or 0,
            'selected_months': self.request.GET.getlist('months'),
            'search_query': self.request.GET.get('search', ''),
            'year': self._get_selected_year(user_transactions),
        })

        # Amount filter context
        context['selected_amount'] = self.request.GET.get('amount', '')
        context['selected_amount_operator'] = self.request.GET.get('amount_operator', 'eq')

        return context
