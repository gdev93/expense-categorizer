import datetime
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.aggregates import StringAgg
from django.core.exceptions import BadRequest
from django.db import transaction
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
    uncategorized_transaction: QuerySet  # Sidebar/Widget data

    # Stats
    total_count: int
    total_amount: float
    category_count: int

    # View Data
    merchant_summary: Any  # Paginated list for merchant view
    transactions: Any  # Paginated list for transaction view

    selected_manual_insert: bool = False
    selected_months: list[str] = field(default_factory=list)
    view_type: str = 'list'
    upload_file: Optional[UploadFile] = None
    selected_amount: Optional[float] = None
    selected_amount_operator: str = 'eq'
    year: int = datetime.datetime.now().year
    paginate_by: int = 25

    def to_context(self) -> dict[str, Any]:
        """Convert dataclass to context dictionary"""
        return asdict(self)


class TransactionListView(LoginRequiredMixin, ListView, TransactionFilterMixin):
    """Display list of transactions with filtering and pagination"""
    model = Transaction
    template_name = 'transactions/transaction_list.html'
    context_object_name = 'transactions'

    # Default pagination if not specified in filters
    paginate_by = 25

    def get_paginate_by(self, queryset):
        # Recupera il valore dal filtro o usa il default della classe
        filters = self.get_transaction_filters()
        return filters.paginate_by

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['transactions/components/transaction_list_htmx.html']
        return [self.template_name]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        merchant_id = request.POST.get('merchant_id')
        new_category_id = request.POST.get('new_category_id')

        if not merchant_id or not new_category_id:
            raise BadRequest("Merchant ID and Category ID are required.")

        merchant = get_object_or_404(Merchant, id=merchant_id, user=self.request.user)
        new_category = get_object_or_404(Category, id=new_category_id, user=self.request.user)

        # Update all transactions of this merchant
        transactions_to_update = Transaction.objects.filter(
            user=self.request.user,
            merchant=merchant,
        )

        upload_file_id = self.kwargs.get('upload_file_id') or self.request.GET.get('upload_file')
        if upload_file_id:
            transactions_to_update = transactions_to_update.filter(upload_file_id=upload_file_id)

        transactions_to_update.update(category=new_category, status='categorized', modified_by_user=True)

        create_rule(merchant, new_category, self.request.user)

        messages.success(self.request,
                         f"Tutte le spese di '{merchant.name}' sono state categorizzate come '{new_category.name}'.")

        return redirect(request.META.get('HTTP_REFERER', 'transaction_list'))

    def get_queryset(self):
        """
        Restituisce il queryset filtrato.
        Se view_type è 'merchant', restituisce un queryset di dizionari (values) aggregati.
        """
        filters = self.get_transaction_filters()
        if filters.view_type == 'merchant':
            queryset = self.get_transaction_filter_query()
            
            # Subquery to check if there are merchants with uncategorized transactions
            merchants_with_uncategorized = queryset.filter(
                status='uncategorized'
            ).values_list('merchant_id', flat=True).distinct()
            
            return queryset.exclude(
                merchant_id__in=merchants_with_uncategorized
            ).values(
                'merchant__id'
            ).annotate(
                number_of_transactions=Count('id'),
                total_spent=Sum('amount'),  # Questo è il campo da sommare per i totali
                is_uncategorized=Value(0, output_field=IntegerField()),
                categories_list=StringAgg('category__name', delimiter=', ', distinct=True),
                category_id=Max('category__id'),
                merchant__encrypted_name=Max('merchant__encrypted_name')
            ).order_by('-number_of_transactions')

        return self.get_transaction_filter_query()

    def get_context_data(self, **kwargs):
        """Add extra context data"""
        context = super().get_context_data(**kwargs)
        filters = self.get_transaction_filters()

        # 1. Dati di riferimento
        categories = list(Category.objects.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        ).order_by('name').values('id', 'name'))

        # 2. Sidebar / Widget dati (Uncategorized)
        uncategorized_transaction = Transaction.objects.filter(
            user=self.request.user,
            status='uncategorized',
            transaction_type='expense'
        ).select_related('upload_file')

        if filters.view_type == 'merchant':
            # Identify merchants with uncategorized transactions
            merchant_filter_query = self.get_transaction_filter_query()
            
            # This identifies merchant IDs that have at least one uncategorized transaction
            # within the current filter context
            merchants_with_uncategorized = merchant_filter_query.filter(
                status='uncategorized'
            ).values_list('merchant_id', flat=True).distinct()
            
            # We want to show these merchants in the "Uncategorized" section of merchant view
            uncategorized_merchants = merchant_filter_query.filter(
                merchant_id__in=merchants_with_uncategorized
            ).values(
                'merchant__id'
            ).annotate(
                number_of_transactions=Count('id'),
                total_spent=Sum('amount'),
                is_uncategorized=Value(1, output_field=IntegerField()),
                categories_list=StringAgg('category__name', delimiter=', ', distinct=True),
                category_id=Max('category__id'),
                merchant__encrypted_name=Max('merchant__encrypted_name')
            ).order_by('-number_of_transactions')
        else:
            uncategorized_merchants = []

        upload_file = None
        if filters.upload_file_id:
            uncategorized_transaction = uncategorized_transaction.filter(upload_file_id=filters.upload_file_id)
            upload_file = get_object_or_404(UploadFile, id=filters.upload_file_id, user=self.request.user)


        full_queryset = self.object_list

        total_count = full_queryset.count()

        if filters.view_type == 'merchant':
            total_amount = full_queryset.aggregate(total=Sum('total_spent'))['total'] or 0
        else:
            total_amount = full_queryset.aggregate(total=Sum('amount'))['total'] or 0

        category_count = full_queryset.values('category').distinct().count()

        # 4. Gestione dati paginati
        # context['page_obj'] contiene l'oggetto pagina di Django (con metadati per paginazione)
        paginated_data = context.get('page_obj')

        transaction_list_context = TransactionListContextData(
            categories=categories,
            selected_status=filters.status,
            selected_upload_file=filters.upload_file_id or '',
            search_query=filters.search,
            uncategorized_transaction=uncategorized_transaction,

            # Stats calcolate correttamente
            total_count=total_count,
            total_amount=total_amount,
            category_count=category_count,

            selected_categories=filters.category_ids,
            selected_months=[str(m) for m in filters.months],
            selected_manual_insert=filters.manual_insert,
            view_type=filters.view_type,
            upload_file=upload_file,
            selected_amount=filters.amount,
            selected_amount_operator=filters.amount_operator,
            year=filters.year,

            # Assegna i dati paginati al campo corretto
            merchant_summary=paginated_data if filters.view_type == 'merchant' else None,
            transactions=paginated_data,
            paginate_by=self.get_paginate_by(full_queryset)
        )
        context['uncategorized_merchants'] = uncategorized_merchants
        
        context.update(transaction_list_context.to_context())
        return context