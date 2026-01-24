from django.core.exceptions import BadRequest
from django.db.models import Q
from django.views import View

from api.models import Transaction
from api.views.mixins import MonthYearFilterMixin


class TransactionFilterMixin(MonthYearFilterMixin, View):
    def get_transaction_filter_query(self):
        queryset = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense',
        ).select_related('category', 'merchant', 'upload_file').order_by('-transaction_date', '-created_at')

        # Filter by category
        category_ids = self.request.GET.getlist('category') or self.request.GET.getlist('categories')
        if category_ids and any(category_ids):
            queryset = queryset.filter(category_id__in=category_ids)

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

        selected_year, selected_months = self.get_year_and_months()
        if not upload_file_id:
            queryset = queryset.filter(transaction_date__year=selected_year)

        if any(selected_months):
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
