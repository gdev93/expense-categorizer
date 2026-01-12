import datetime
from dataclasses import dataclass, asdict, field
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.db.models import QuerySet
from django.views.generic import ListView

from api.models import Transaction, Category, Rule, CsvUpload


@dataclass
class TransactionListContextData:
    """Context data for transaction list view"""
    categories: list[dict[str, Any]]
    selected_category: str
    selected_status: str
    selected_csv_upload: str
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
    paginate_by = 50

    def get_queryset(self):
        """Filter transactions based on user and query parameters"""
        queryset = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense',
            category__isnull=False,
            merchant_id__isnull=False
        ).select_related('category', 'merchant', 'csv_upload').order_by('-transaction_date', '-created_at')

        # Filter by category
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # Filter by csv_upload
        csv_upload_id = self.request.GET.get('csv_upload')
        if csv_upload_id:
            queryset = queryset.filter(csv_upload_id=csv_upload_id)

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
                pass

        # Search filter
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(merchant_raw_name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # Year logic
        try:
            get_year = self.request.GET.get('year')
            if get_year:
                selected_year = int(get_year)
            else:
                # Fallback to most recent transaction year if no year provided
                first_t = queryset.first()
                selected_year = first_t.transaction_date.year if first_t else datetime.datetime.now().year
        except (TypeError, ValueError, AttributeError):
            selected_year = datetime.datetime.now().year

        queryset = queryset.filter(transaction_date__year=selected_year)

        # Filter by months
        selected_months = self.request.GET.getlist('months')
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

        return queryset

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)

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
        ).select_related('csv_upload')

        csv_upload_id = self.request.GET.get('csv_upload', '')
        if csv_upload_id:
            uncategorized_transaction = uncategorized_transaction.filter(csv_upload_id=csv_upload_id)

        transaction_list_context = TransactionListContextData(
            categories=categories,
            selected_status=self.request.GET.get('status', ''),
            selected_csv_upload=csv_upload_id,
            search_query=self.request.GET.get('search', ''),
            uncategorized_transaction=uncategorized_transaction,
            total_count=user_transactions.count(),
            total_amount=user_transactions.filter(status="categorized").aggregate(
                total=Sum('amount')
            )['total'] or 0,
            category_count=user_transactions.values('category').distinct().count(),
            rules=Rule.objects.filter(user=self.request.user, is_active=True),
            selected_category=self.request.GET.get('category', ''),
            selected_months=self.request.GET.getlist('months')
        )
        context.update(transaction_list_context.to_context())

        # Add amount filter context
        context['selected_amount'] = self.request.GET.get('amount', '')
        context['selected_amount_operator'] = self.request.GET.get('amount_operator', 'eq')
        context['year'] = getattr(self, 'selected_year', datetime.datetime.now().year)

        return context

class IncomeListView(LoginRequiredMixin, ListView):
    """Display list of income transactions with filtering and pagination"""
    model = Transaction
    template_name = 'transactions/transaction_income_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

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
                pass

        # Year logic
        try:
            get_year = self.request.GET.get('year')
            if get_year:
                selected_year = int(get_year)
            else:
                # Fallback to most recent transaction year if no year provided
                first_t = queryset.first()
                selected_year = first_t.transaction_date.year if first_t else datetime.datetime.now().year
        except (TypeError, ValueError, AttributeError):
            selected_year = datetime.datetime.now().year

        self.selected_year = selected_year
        queryset = queryset.filter(transaction_date__year=selected_year)

        # Filter by months
        selected_months = self.request.GET.getlist('months')
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
            'year': getattr(self, 'selected_year', datetime.datetime.now().year),
        })

        # Amount filter context
        context['selected_amount'] = self.request.GET.get('amount', '')
        context['selected_amount_operator'] = self.request.GET.get('amount_operator', 'eq')

        return context
