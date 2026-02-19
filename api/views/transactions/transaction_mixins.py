import os
from dataclasses import dataclass, field
from typing import List, Optional
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.views import View
from api.models import Transaction
from api.privacy_utils import generate_blind_index
from api.views.mixins import MonthYearFilterMixin


@dataclass
class TransactionFilterState:
    """
    Data container for transaction filters.
    Handles extraction from request and session management.
    """
    year: int
    months: List[int]
    category_ids: List[str] = field(default_factory=list)
    upload_file_id: Optional[str] = None
    amount: Optional[float] = None
    amount_operator: str = 'eq'
    search: str = ''
    view_type: str = 'list'
    status: str = ''
    manual_insert: bool = False
    paginate_by: int = 25

    @classmethod
    def from_request(cls, request: HttpRequest, year: int, months: List[int],
                     upload_file_id: Optional[str] = None) -> 'TransactionFilterState':
        """
        Factory method to build the filter state from GET params or Session.
        It also handles the side effect of updating the session.
        """
        reset = request.GET.get('reset') == "1"

        # Session keys mapping
        session_map = {
            'category_ids': 'filter_category',
            'amount': 'filter_amount',
            'amount_operator': 'filter_amount_operator',
            'search': 'filter_search',
            'view_type': 'filter_view_type',
            'status': 'filter_status',
            'manual_insert': 'filter_manual_insert',
            'paginate_by': 'filter_paginate_by',
        }

        if reset:
            for key in session_map.values():
                if key in request.session:
                    del request.session[key]

        # Helper to extract value (GET > Session > Default) and update session
        def get_value(param_name, session_key, default, cast_func=None):
            value = default

            # Check GET first
            if param_name in request.GET:
                raw_value = request.GET.get(param_name)
                # Handle boolean specifically for checkboxes usually sending 'on' or 'true'
                if cast_func == bool:
                    value = raw_value in ('true', 'on', '1')
                else:
                    value = raw_value
                request.session[session_key] = value
            # Fallback to session (if not reset)
            elif not reset and session_key in request.session:
                value = request.session[session_key]

            # Apply casting if provided and value is not None
            if cast_func and value is not None and cast_func != bool:
                try:
                    return cast_func(value)
                except (ValueError, TypeError):
                    return default
            return value

        # 1. Category (Special case: list handling)
        category_ids = []
        if 'category' in request.GET or 'categories' in request.GET:
            category_ids = [cid for cid in (request.GET.getlist('category') or request.GET.getlist('categories')) if cid]
            request.session['filter_category'] = category_ids
        elif not reset:
            category_ids = request.session.get('filter_category', [])

        # 2. Upload File (Not stored in session usually, passed from View kwargs)
        file_id = upload_file_id or request.GET.get('upload_file')

        # 3. Determine default pagination based on device
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        is_mobile = any(keyword in user_agent for keyword in
                        ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 'iemobile', 'opera mini'])
        default_pagination = 10 if is_mobile else int(os.environ.get('DEFAULT_PAGINATION', 25))

        # 4. Build the object
        return cls(
            year=year,
            months=months,
            category_ids=category_ids,
            upload_file_id=file_id,
            amount=get_value('amount', 'filter_amount', None, float),
            amount_operator=get_value('amount_operator', 'filter_amount_operator', 'eq', str),
            search=get_value('search', 'filter_search', '', str),
            view_type=get_value('view_type', 'filter_view_type', 'list', str),
            status=get_value('status', 'filter_status', '', str),
            manual_insert=get_value('manual_insert', 'filter_manual_insert', False, bool),
            paginate_by=get_value('paginate_by', 'filter_paginate_by', default_pagination, int)
        )


class TransactionFilterMixin(MonthYearFilterMixin, View):

    def get_transaction_filters(self) -> TransactionFilterState:
        """
        Delegates the logic to the dataclass factory method.
        """
        # Get date filters from the inherited mixin
        year, months = self.get_year_and_months()

        # Get optional kwargs if available (e.g., from URL path)
        upload_file_id = self.kwargs.get('upload_file_id')

        return TransactionFilterState.from_request(
            request=self.request,
            year=year,
            months=months,
            upload_file_id=upload_file_id
        )

    def get_transaction_filter_query(self) -> QuerySet:
        queryset = Transaction.objects.filter(
            user=self.request.user,
            transaction_type='expense',
        ).select_related('category', 'merchant', 'upload_file').order_by('-transaction_date', '-created_at')

        # Retrieve the dataclass instance
        filters = self.get_transaction_filters()

        # 1. Filter by Category
        if filters.category_ids:
            queryset = queryset.filter(category_id__in=filters.category_ids)

        # 2. Filter by Upload File
        if filters.upload_file_id:
            queryset = queryset.filter(upload_file_id=filters.upload_file_id)

        # 3. Filter by Amount (Disabled due to encryption)
        # SQL-level filtering on encrypted amount is not possible.

        # 4. Filter by Search
        if filters.search:
            search_hash = generate_blind_index(filters.search)
            queryset = queryset.filter(
                Q(merchant__name_hash=search_hash) |
                Q(description_hash=search_hash)
            )

        # 5. Filter by Date
        # Only apply year filter if we are not looking at a specific file
        if filters.year and not filters.upload_file_id:
            queryset = queryset.filter(transaction_date__year=filters.year)

        if filters.months:
            queryset = queryset.filter(transaction_date__month__in=filters.months)

        # 6. Filter by Status
        if filters.status:
            queryset = queryset.filter(status=filters.status)

        # 7. Filter by Manual Insert
        if filters.manual_insert:
            queryset = queryset.filter(manual_insert=True)

        # 8. View Type logic
        if filters.view_type == 'list':
            # If a status filter is explicitly applied, we don't want to force-exclude uncategorized
            if filters.status:
                return queryset
            return queryset.filter(category__isnull=False, merchant_id__isnull=False)

        return queryset