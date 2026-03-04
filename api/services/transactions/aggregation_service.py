import decimal
from decimal import Decimal
from functools import wraps
from typing import Iterable, Dict, Tuple, Any, List

from django.contrib.auth.models import User
from django.db.models import QuerySet

from api.models import Transaction, YearlyMonthlyUserRollup, CategoryRollup

def optimize_total_amount(func):
    """
    Decorator that intercepts aggregation calls to use the YearlyUserRollup table
    when default filters are applied, avoiding expensive on-the-fly calculations
    of encrypted data.
    """

    @wraps(func)
    def wrapper(user: User, filters: Any, queryset: Any, *args: Any, **kwargs: Any) -> Any:
        # 1. Early exit if requirements are not met
        is_default = getattr(filters, 'is_default_filter', False)
        year = getattr(filters, 'year', None)

        if not (is_default and year):
            return func(user, filters, queryset, *args, **kwargs)

        months: List[int] = getattr(filters, 'months', [])
        category_ids: List[int] = getattr(filters, 'category_ids', [])

        # 2. Logic for CategoryRollup
        if category_ids:
            query = CategoryRollup.objects.filter(
                user=user,
                year=year,
                category_id__in=category_ids
            )
            if months:
                query = query.filter(month_number__in=months)

            # Calculate sum in memory (decryption happens on access)
            return sum(item.total_spent for item in query)

        # 3. Logic for Yearly/Monthly Rollup
        if months:
            monthly_query = YearlyMonthlyUserRollup.objects.filter(
                user=user,
                by_year=year,
                month_number__in=months
            )
            return sum(item.total_amount_expense_by_month for item in monthly_query)

        # 4. Yearly total (single record)
        rollup_yearly = YearlyMonthlyUserRollup.objects.filter(
            user=user,
            by_year=year,
            month_number__isnull=True
        ).first()

        if rollup_yearly:
            return rollup_yearly.total_amount_expense_by_year

        # Fallback to original function
        return func(user, filters, queryset, *args, **kwargs)

    return wrapper

class TransactionAggregationService:
    """Service to handle aggregations of transactions with encrypted amounts."""

    @staticmethod
    @optimize_total_amount
    def calculate_total_amount(user, filters, queryset_or_iterable: list[Transaction] | QuerySet[Transaction, Transaction]) -> Decimal:
        """Calculate the total amount of transactions by using its amount property."""
        total_amount = Decimal('0')

        for item in queryset_or_iterable:
            val = item.amount
            if val:
                total_amount += val
        return total_amount

    @staticmethod
    def calculate_merchant_sums(queryset: QuerySet[Transaction, Transaction], merchant_ids: Iterable[int]) -> Dict[
        int, Decimal]:
        """Calculate the sum of transactions for each merchant in merchant_ids."""
        sums = {m_id: Decimal('0') for m_id in merchant_ids}

        tx_data = queryset.filter(merchant_id__in=merchant_ids)
        for tx in tx_data:
            m_id = tx.merchant_id
            val = tx.amount
            if val:
                sums[m_id] += val
        return sums

    @staticmethod
    def calculate_category_sums(queryset: QuerySet[Transaction, Transaction], category_ids: Iterable[int]) -> Dict[
        int, Decimal]:
        """Calculate the sum of transactions for each category in category_ids."""
        sums = {c_id: Decimal('0') for c_id in category_ids}

        tx_data = queryset.filter(category_id__in=category_ids)
        for tx in tx_data:
            c_id = tx.category_id
            val = tx.amount
            if val:
                sums[c_id] += val
        return sums

    @staticmethod
    def calculate_category_monthly_sums(queryset: QuerySet[Transaction, Transaction]) -> Dict[Tuple[str, int], Decimal]:
        """Calculate the sum of transactions grouped by category name and month."""
        from collections import defaultdict
        grouped_data = defaultdict(Decimal)

        tx_data = queryset.select_related('category')
        
        for tx in tx_data:
            cat_name = tx.category.name if tx.category else None
            month = tx.transaction_date.month if tx.transaction_date else None
            if not cat_name or not month:
                continue

            val = tx.amount
            if val:
                grouped_data[(cat_name, month)] += val
        return grouped_data
