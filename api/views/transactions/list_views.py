import datetime
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum, Exists, OuterRef
from django.views.generic import ListView
from dataclasses import dataclass, asdict, field
from typing import Any
from django.db.models import QuerySet

from api.models import Transaction, Category, Rule

@dataclass
class TransactionListContextData:
    """Context data for transaction list view"""
    categories: list[dict[str, Any]]
    selected_category: str
    selected_status: str
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
    default_categories: list[
        str] = "Casa,Spesa,Auto,Carburante,Vita sociale,Pizza,Regali,Vacanze,Sport,Bollette,Scuola,Bambini,Shopping,Abbonamenti,Affitto,Baby-sitter,Trasporti,Spese mediche,Partita Iva, Bonifico".split(
        ',')

    def get_queryset(self):
        """Filter transactions based on user and query parameters"""
        queryset = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense',
            category__isnull=False,
            merchant_id__isnull=False  # Filtra per escludere i valori NULL
        ).select_related('category', 'merchant').order_by('-transaction_date', '-created_at')

        # Filter by category
        category_id = self.request.GET.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

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

        # Filter by months
        selected_months = self.request.GET.getlist('months')
        if selected_months:
            # Interpret months as numeric month values for the selected year
            try:
                selected_year_qs = int(self.request.GET.get('year') or datetime.datetime.now().year)
            except (TypeError, ValueError):
                selected_year_qs = datetime.datetime.now().year

            month_queries = Q()
            for month_str in selected_months:
                try:
                    month = int(month_str)
                    month_queries |= Q(
                        transaction_date__year=selected_year_qs,
                        transaction_date__month=month
                    )
                except (ValueError, TypeError):
                    pass
            if month_queries:
                queryset = queryset.filter(month_queries)

        # Search filter
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(merchant_raw_name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        return queryset

    def get_available_months(self):
        """Get list of available months from transactions"""
        transactions = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense'
        ).dates('transaction_date', 'month', order='DESC')

        months = []
        for date in transactions:
            months.append({
                'value': date.strftime('%Y-%m'),
                'label': date.strftime('%B %Y'),
                'label_it': self.get_italian_month_name(date)
            })
        return months

    @staticmethod
    def get_italian_month_name(date):
        """Convert date to Italian month name format"""
        italian_months = {
            1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
            5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
            9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
        }
        return f"{italian_months[date.month]} {date.year}"

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)

        # Get all categories for filter dropdown
        categories = list(Category.objects.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        ).order_by('name').values('id', 'name'))

        # Base queryset for user transactions
        user_transactions = self.get_queryset()

        # Apply month filter to summary data if months are selected
        # 'months' values are month numbers (1..12); restrict by selected year from GET 'year'
        selected_months = self.request.GET.getlist('months')
        try:
            first_transaction_date = user_transactions.first()
            selected_year = int(self.request.GET.get('year',
                                                     first_transaction_date.transaction_date.year if first_transaction_date else datetime.datetime.now().year))
        except (TypeError, ValueError):
            selected_year = datetime.datetime.now().year

        if selected_months:
            month_queries = Q()
            for month_str in selected_months:
                try:
                    month = int(month_str)
                    month_queries |= Q(
                        transaction_date__year=selected_year,
                        transaction_date__month=month
                    )
                except (ValueError, TypeError):
                    pass
            if month_queries:
                user_transactions = user_transactions.filter(month_queries)
        transaction_list_context = TransactionListContextData(
            categories=categories,
            selected_status=self.request.GET.get('status', ''),
            search_query=self.request.GET.get('search', ''),
            uncategorized_transaction=Transaction.objects.filter(user=self.request.user, status='uncategorized',
                                                                 transaction_type='expense'),
            total_count=user_transactions.count(),
            total_amount=user_transactions.filter(status="categorized").aggregate(
                total=Sum('amount')
            )['total'] or 0,
            category_count=user_transactions.values('category').distinct().count(),
            rules=Rule.objects.filter(user=self.request.user, is_active=True),
            selected_category=self.request.GET.get('category', ''),
            # available_months is now provided by a global context processor
            selected_months=selected_months
        )
        context.update(transaction_list_context.to_context())

        # Add amount filter context
        context['selected_amount'] = self.request.GET.get('amount', '')
        context['selected_amount_operator'] = self.request.GET.get('amount_operator', 'eq')

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

        # Filter by months (month numbers for selected year)
        selected_months = self.request.GET.getlist('months')
        if selected_months:
            try:
                selected_year_qs = int(self.request.GET.get('year') or datetime.datetime.now().year)
            except (TypeError, ValueError):
                selected_year_qs = datetime.datetime.now().year

            month_queries = Q()
            for month_str in selected_months:
                try:
                    month = int(month_str)
                    month_queries |= Q(
                        transaction_date__year=selected_year_qs,
                        transaction_date__month=month
                    )
                except (ValueError, TypeError):
                    pass
            if month_queries:
                queryset = queryset.filter(month_queries)

        # Search filter (on description only, incomes typically lack merchant)
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(description__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Base queryset possibly filtered by months already
        user_transactions = self.get_queryset()

        # Selected months in context
        selected_months = self.request.GET.getlist('months')

        # Totals
        context.update({
            'total_count': user_transactions.count(),
            'total_amount': user_transactions.filter(status="categorized").aggregate(total=Sum('amount'))['total'] or 0,
            'selected_months': selected_months,
            'search_query': self.request.GET.get('search', ''),
        })

        # Amount filter context
        context['selected_amount'] = self.request.GET.get('amount', '')
        context['selected_amount_operator'] = self.request.GET.get('amount_operator', 'eq')

        return context
