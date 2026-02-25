from decimal import Decimal
from functools import wraps
from typing import Iterable, Dict, Tuple

from django.db import transaction
from django.db.models import QuerySet

from api.models import Transaction


def optimize_total_amount(func):
    """
    Decorator that intercepts aggregation calls to use the YearlyUserRollup table
    when default filters are applied, avoiding expensive on-the-fly calculations
    of encrypted data.
    """

    @wraps(func)
    def wrapper(user, filters, queryset, *args, **kwargs):
        # Check if filters are at their default values using the dataclass property
        if getattr(filters, 'is_default_filter', False):
            from api.models import YearlyMonthlyUserRollup

            year = getattr(filters, 'year', None)

            # Wrap in a transaction to safely use select_for_update if needed,
            # though for simple reads, a standard filter is usually enough.
            with transaction.atomic():
                if year:
                    rollup_query = YearlyMonthlyUserRollup.objects.filter(
                        user=user,
                        by_year=year
                    )
                    months = getattr(filters, 'months', None)
                    if any(months):
                        rollup_query = rollup_query.filter(month_number__in=months)
                        return sum([rollup.total_amount_expense_by_month for rollup in rollup_query])
                    else:
                        rollup_yearly = rollup_query.filter(month_number__isnull=True).first()
                        return rollup_yearly.total_amount_expense_by_year if rollup_yearly else func(user, filters, queryset, *args, **kwargs)
                else:
                    return func(user, filters, queryset, *args, **kwargs)

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


class RollupService:
    """Service to handle rollup table updates."""

    @staticmethod
    def update_user_rollup(user, years_months: Iterable[Tuple[int, int | None]]):
        """
        Update the YearlyMonthlyUserRollup for a given user and a list of (year, month) tuples.
        Also updates the yearly totals for those years.
        """
        from api.models import Transaction, YearlyMonthlyUserRollup

        # We need to update monthly records and the yearly summary record (where month_number is None)
        years_to_update = set()
        month_combinations = set()

        for year, month in years_months:
            if year:
                years_to_update.add(year)
                if month:
                    month_combinations.add((year, month))

        # 1. Update Monthly Records
        for year, month in month_combinations:
            transactions = Transaction.objects.filter(
                user=user,
                transaction_date__year=year,
                transaction_date__month=month
            )

            total_expense = Decimal('0.00')
            total_income = Decimal('0.00')

            for tx in transactions:
                amount = tx.amount
                if amount:
                    if tx.transaction_type == 'expense':
                        total_expense += amount
                    elif tx.transaction_type == 'income':
                        total_income += amount

            # For monthly record, we don't necessarily need to store the yearly total here,
            # or we can decide to store it. Given the previous structure, let's keep it simple:
            # Monthly record stores the monthly total.
            YearlyMonthlyUserRollup.objects.update_or_create(
                user=user,
                by_year=year,
                month_number=month,
                defaults={
                    'total_amount_expense_by_month': total_expense,
                    'total_amount_income_by_month': total_income,
                }
            )

        # 2. Update Yearly Summary Records (month_number=None)
        for year in years_to_update:
            transactions = Transaction.objects.filter(
                user=user,
                transaction_date__year=year
            )

            total_expense = Decimal('0.00')
            total_income = Decimal('0.00')

            for tx in transactions:
                amount = tx.amount
                if amount:
                    if tx.transaction_type == 'expense':
                        total_expense += amount
                    elif tx.transaction_type == 'income':
                        total_income += amount

            YearlyMonthlyUserRollup.objects.update_or_create(
                user=user,
                by_year=year,
                month_number=None,
                defaults={
                    'total_amount_expense_by_year': total_expense,
                    'total_amount_income_by_year': total_income
                }
            )

    @staticmethod
    def update_user_yearly_rollup(user, years: Iterable[int]):
        """Legacy method to update only yearly rollups."""
        RollupService.update_user_rollup(user, [(year, None) for year in years])
