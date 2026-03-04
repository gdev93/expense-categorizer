from decimal import Decimal
from django.db.models import Count, Q, QuerySet

from api.models import Category, Transaction
from api.services.transactions.aggregation_service import TransactionAggregationService
from api.views.mixins import MonthYearFilterMixin

class CategoryEnrichedMixin(MonthYearFilterMixin):
    def get_category_filters(self):
        # Check if a reset was requested
        year, months = self.get_year_and_months()
        if self.request.GET.get('reset') == '1':
            self.request.session.pop('filter_category_search', None)
            self.request.session.pop('filter_category_selected', None)
            # If your Mixin stores months/years in session, clear them here too
            return {'search': '', 'selected_category_ids': [], 'year': year, 'months': months}

        filters = {}

        # Search Filter
        if 'search' in self.request.GET:
            filters['search'] = self.request.GET.get('search')
            self.request.session['filter_category_search'] = filters['search']
        else:
            filters['search'] = self.request.session.get('filter_category_search', '')

        # Categories Filter
        if 'categories' in self.request.GET:
            filters['selected_category_ids'] = self.request.GET.getlist('categories')
            self.request.session['filter_category_selected'] = filters['selected_category_ids']
        else:
            filters['selected_category_ids'] = self.request.session.get('filter_category_selected', [])

        filters['year']=year
        filters['months']=months
        return filters

    def get_enriched_category_queryset(self, base_category_queryset:QuerySet[Category,Category]):
        filters = self.get_category_filters()
        filter_q = Q(transactions__transaction_date__year=filters['year'])
        if filters['months']:
            filter_q &= Q(transactions__transaction_date__month__in=filters['months'])

        # Group and Count in DB, Sum in Python
        categories = base_category_queryset.annotate(
            transaction_count=Count(
                'transactions',
                filter=filter_q
            )
        ).order_by('name')
        
        # Adding transaction_amount in Python
        categories_list = list(categories)
        category_ids = [c.id for c in categories_list]
        
        tx_filter = Q(category_id__in=category_ids, transaction_date__year=filters['year'])
        if filters['months']:
            tx_filter &= Q(transaction_date__month__in=filters['months'])
            
        # Optimization: Fetch only necessary fields
        transactions_queryset = Transaction.objects.filter(tx_filter)
        sums = TransactionAggregationService.calculate_category_sums(transactions_queryset, category_ids)
        
        for c in categories_list:
            c.transaction_amount = sums.get(c.id, Decimal('0'))

        return categories_list
