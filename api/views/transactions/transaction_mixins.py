from django.core.exceptions import BadRequest
from django.db.models import Q
from django.views import View

from api.models import Transaction
from api.views.mixins import MonthYearFilterMixin


class TransactionFilterMixin(MonthYearFilterMixin, View):
    def get_transaction_filters(self):
        """
        Retrieves filters from GET parameters or session.
        Returns a dictionary of filters.
        """
        filters = {}

        # 1. Category
        if 'category' in self.request.GET or 'categories' in self.request.GET:
            filters['category_ids'] = self.request.GET.getlist('category') or self.request.GET.getlist('categories')
            self.request.session['filter_category'] = filters['category_ids']
        else:
            filters['category_ids'] = self.request.session.get('filter_category', [])

        # 2. Upload File (Don't put in session as it's often page-specific)
        filters['upload_file_id'] = self.kwargs.get('upload_file_id') or self.request.GET.get('upload_file')

        # 3. Amount
        if 'amount' in self.request.GET:
            filters['amount'] = self.request.GET.get('amount')
            self.request.session['filter_amount'] = filters['amount']
        else:
            filters['amount'] = self.request.session.get('filter_amount')

        if 'amount_operator' in self.request.GET:
            filters['amount_operator'] = self.request.GET.get('amount_operator', 'eq')
            self.request.session['filter_amount_operator'] = filters['amount_operator']
        else:
            filters['amount_operator'] = self.request.session.get('filter_amount_operator', 'eq')

        # 4. Search
        if 'search' in self.request.GET:
            filters['search'] = self.request.GET.get('search')
            self.request.session['filter_search'] = filters['search']
        else:
            filters['search'] = self.request.session.get('filter_search', '')

        # 5. View Type
        if 'view_type' in self.request.GET:
            filters['view_type'] = self.request.GET.get('view_type', 'list')
            self.request.session['filter_view_type'] = filters['view_type']
        else:
            filters['view_type'] = self.request.session.get('filter_view_type', 'list')

        # 6. Status
        if 'status' in self.request.GET:
            filters['status'] = self.request.GET.get('status', '')
            self.request.session['filter_status'] = filters['status']
        else:
            filters['status'] = self.request.session.get('filter_status', '')

        # 7. Year and Months (from MonthYearFilterMixin)
        filters['year'], filters['months'] = self.get_year_and_months()

        return filters

    def get_transaction_filter_query(self):
        queryset = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense',
        ).select_related('category', 'merchant', 'upload_file').order_by('-transaction_date', '-created_at')

        filters = self.get_transaction_filters()

        # Filter by category
        if filters['category_ids'] and any(filters['category_ids']):
            queryset = queryset.filter(category_id__in=filters['category_ids'])

        # Filter by upload_file
        if filters['upload_file_id']:
            queryset = queryset.filter(upload_file_id=filters['upload_file_id'])

        # Filter by amount
        if filters['amount']:
            try:
                amount_value = float(filters['amount'])
                op = filters['amount_operator']
                if op == 'eq':
                    queryset = queryset.filter(amount=amount_value)
                elif op == 'gt':
                    queryset = queryset.filter(amount__gt=amount_value)
                elif op == 'gte':
                    queryset = queryset.filter(amount__gte=amount_value)
                elif op == 'lt':
                    queryset = queryset.filter(amount__lt=amount_value)
                elif op == 'lte':
                    queryset = queryset.filter(amount__lte=amount_value)
            except (ValueError, TypeError):
                raise BadRequest("Invalid amount format.")

        # Search filter
        if filters['search']:
            queryset = queryset.filter(
                Q(merchant__name__icontains=filters['search']) |
                Q(merchant_raw_name__icontains=filters['search']) |
                Q(description__icontains=filters['search'])
            )

        # Year and Month filters
        if not filters['upload_file_id']:
            queryset = queryset.filter(transaction_date__year=filters['year'])

        if any(filters['months']):
            month_queries = Q()
            for month in filters['months']:
                month_queries |= Q(transaction_date__month=month)
            if month_queries:
                queryset = queryset.filter(month_queries)

        # Status filter
        if filters['status']:
            queryset = queryset.filter(status=filters['status'])

        # For the main list view, we only want categorized transactions
        # to avoid duplication with the uncategorized section in the template.
        if filters['view_type'] == 'list':
            return queryset.filter(category__isnull=False, merchant_id__isnull=False)

        return queryset
