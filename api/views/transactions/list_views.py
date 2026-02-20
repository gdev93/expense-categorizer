import datetime
import os
from dataclasses import dataclass, asdict, field
from decimal import Decimal
from typing import Any, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.postgres.aggregates import StringAgg
from django.core.exceptions import BadRequest
from django.db import transaction
from django.db.models import Q, Count, Max, Value, IntegerField
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView

from api.models import Transaction, Category, UploadFile, Merchant
from api.privacy_utils import decrypt_value
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
    paginate_by = int(os.getenv("DEFAULT_PAGINATION", "25"))

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
        filters = self.get_transaction_filters()
        queryset = self.get_transaction_filter_query()

        if filters.view_type == 'merchant':
            # Subquery to check if there are merchants with uncategorized transactions
            merchants_with_uncategorized = queryset.filter(
                status='uncategorized'
            ).values_list('merchant_id', flat=True).distinct()

            # Base aggregation (Removed Sum)
            merchants_query = queryset.exclude(
                merchant_id__in=merchants_with_uncategorized
            ).values(
                'merchant__id'
            ).annotate(
                number_of_transactions=Count('id'),
                is_uncategorized=Value(0, output_field=IntegerField()),
                categories_list=StringAgg('category__name', delimiter=', ', distinct=True),
                category_id=Max('category__id'),
                merchant__encrypted_name=Max('merchant__encrypted_name')
            ).order_by('-number_of_transactions')

            # Always return the query for merchants, ignoring the amount filter if present.
            # This allows database-level pagination.
            self.full_merchant_count = merchants_query.count()
            return merchants_query

        # If view_type is 'list', apply amount filter in Python
        if filters.amount is not None:
            target_amount = Decimal(str(filters.amount))
            # Se abbiamo l'amount filter dobbiamo caricare tutto per filtrare in Python
            # Usiamo iterator() o values() per mitigare l'uso di memoria se possibile
            # ma ListView ha bisogno di un oggetto che supporti len() o un QuerySet.
            filtered_list = [tx for tx in queryset if tx.amount == target_amount]
            self.full_merchant_count = len(filtered_list)
            return filtered_list

        return queryset

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
            
            merchants_with_uncategorized = merchant_filter_query.filter(
                status='uncategorized'
            ).values_list('merchant_id', flat=True).distinct()
            
            uncategorized_merchants_query = merchant_filter_query.filter(
                merchant_id__in=merchants_with_uncategorized
            ).values(
                'merchant__id'
            ).annotate(
                number_of_transactions=Count('id'),
                is_uncategorized=Value(1, output_field=IntegerField()),
                categories_list=StringAgg('category__name', delimiter=', ', distinct=True),
                category_id=Max('category__id'),
                merchant__encrypted_name=Max('merchant__encrypted_name')
            ).order_by('-number_of_transactions')

            uncategorized_merchants = list(uncategorized_merchants_query)
            
            # Calculate sums in Python for uncategorized merchants
            uncat_merchant_ids = [m['merchant__id'] for m in uncategorized_merchants if m['merchant__id']]
            uncat_sums = {m_id: Decimal('0') for m_id in uncat_merchant_ids}
            
            uncat_tx_data = merchant_filter_query.filter(merchant_id__in=uncat_merchant_ids).values('merchant_id', 'encrypted_amount')
            for tx in uncat_tx_data:
                m_id = tx['merchant_id']
                val = decrypt_value(tx['encrypted_amount'])
                if val:
                    try:
                        uncat_sums[m_id] += Decimal(val)
                    except Exception:
                        pass
            
            for m in uncategorized_merchants:
                m['total_spent'] = uncat_sums.get(m['merchant__id'], Decimal('0'))
        else:
            uncategorized_merchants = []

        upload_file = None
        if filters.upload_file_id:
            uncategorized_transaction = uncategorized_transaction.filter(upload_file_id=filters.upload_file_id)
            upload_file = get_object_or_404(UploadFile, id=filters.upload_file_id, user=self.request.user)


        full_queryset = self.object_list
        # Se abbiamo impostato full_merchant_count, lo usiamo per il totale (per evitare len() o count() ripetuti)
        total_count = getattr(self, 'full_merchant_count', None)
        if total_count is None:
            total_count = len(full_queryset) if isinstance(full_queryset, list) else full_queryset.count()

        # Per le statistiche globali (total_amount), purtroppo dobbiamo comunque iterare 
        # su tutte le transazioni se vogliamo il totale esatto, ma possiamo farlo in modo più efficiente.
        if filters.view_type == 'merchant':
            # In merchant view, we always calculate the total amount by decrypting all filtered transactions
            # because the amount filter is ignored for this view.
            total_amount = Decimal('0')
            # Recuperiamo solo gli importi di tutte le transazioni filtrate
            amounts_qs = self.get_transaction_filter_query().values('encrypted_amount')
            for tx in amounts_qs:
                val = decrypt_value(tx['encrypted_amount'])
                if val:
                    try:
                        total_amount += Decimal(val)
                    except Exception:
                        pass
        else:
            total_amount = Decimal('0')
            if isinstance(full_queryset, QuerySet):
                it = full_queryset.values('encrypted_amount')
            else:
                it = [{'encrypted_amount': tx.encrypted_amount} for tx in full_queryset]

            for tx in it:
                val = decrypt_value(tx['encrypted_amount'])
                if val:
                    try:
                        total_amount += Decimal(val)
                    except Exception:
                        pass

        category_count = self.get_transaction_filter_query().values('category').distinct().count()

        paginated_data = context.get('page_obj')
        
        # Se siamo in view_type 'merchant', calcoliamo i totali per i merchant nella pagina corrente.
        if filters.view_type == 'merchant':
            # Gli oggetti in paginated_data sono dict provenienti da .values()
            current_page_merchants = list(paginated_data.object_list)
            m_ids = [m['merchant__id'] for m in current_page_merchants if m['merchant__id']]
            
            # Calcoliamo le somme solo per i merchant nella pagina
            page_sums = {m_id: Decimal('0') for m_id in m_ids}
            tx_qs = self.get_transaction_filter_query().filter(merchant_id__in=m_ids).values('merchant_id', 'encrypted_amount')
            
            for tx in tx_qs:
                m_id = tx['merchant_id']
                val = decrypt_value(tx['encrypted_amount'])
                if val:
                    try:
                        page_sums[m_id] += Decimal(val)
                    except Exception:
                        pass
            
            for m in current_page_merchants:
                m['total_spent'] = page_sums.get(m['merchant__id'], Decimal('0'))
            
            # Aggiorniamo l'object_list nel paginator così il template vedrà i total_spent
            paginated_data.object_list = current_page_merchants

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
            year=filters.year,

            # Assegna i dati paginati al campo corretto
            merchant_summary=paginated_data if filters.view_type == 'merchant' else None,
            transactions=paginated_data,
            paginate_by=self.get_paginate_by(full_queryset)
        )
        context['uncategorized_merchants'] = uncategorized_merchants
        
        context.update(transaction_list_context.to_context())
        return context