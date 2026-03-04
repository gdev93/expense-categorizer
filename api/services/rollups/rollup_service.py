from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Tuple

from django.contrib.auth.models import User

from api.models import Transaction, YearlyMonthlyUserRollup, CategoryRollup

class RollupService:
    """Service to handle rollup table updates."""

    @staticmethod
    def update_user_rollup(user: User, years_months: Iterable[Tuple[int, int | None]]) -> None:
        """
        Update the YearlyMonthlyUserRollup for a given user and a list of (year, month) tuples.
        Also updates the yearly totals for those years.
        """

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
    def update_category_rollup(user: User, years_months: Iterable[Tuple[int, int | None]]) -> None:
        """
        Update the CategoryRollup for a given user and a list of (year, month) tuples.
        Also updates the yearly totals for those years.
        """
        years_to_update = set()
        month_combinations = set()

        for year, month in years_months:
            if year:
                years_to_update.add(year)
                if month:
                    month_combinations.add((year, month))

        # 1. Update Monthly Records for Categories
        for year, month in month_combinations:
            transactions = Transaction.objects.filter(
                user=user,
                transaction_date__year=year,
                transaction_date__month=month,
                transaction_type='expense'
            )
            
            category_sums = defaultdict(Decimal)
            for tx in transactions:
                if tx.category_id:
                    val = tx.amount
                    if val:
                        category_sums[tx.category_id] += val
            
            # Categories that now have 0 spent but had a rollup record for this month
            existing_rollups = CategoryRollup.objects.filter(user=user, year=year, month_number=month)
            existing_cat_ids = set(existing_rollups.values_list('category_id', flat=True))
            
            all_involved_cat_ids = existing_cat_ids | set(category_sums.keys())
            
            for category_id in all_involved_cat_ids:
                total_spent = category_sums.get(category_id, Decimal('0.00'))
                CategoryRollup.objects.update_or_create(
                    user=user,
                    category_id=category_id,
                    year=year,
                    month_number=month,
                    defaults={'total_spent': total_spent}
                )

        # 2. Update Yearly Summary Records for Categories (month_number=None)
        for year in years_to_update:
            transactions = Transaction.objects.filter(
                user=user,
                transaction_date__year=year,
                transaction_type='expense'
            )
            
            category_sums = defaultdict(Decimal)
            for tx in transactions:
                if tx.category_id:
                    val = tx.amount
                    if val:
                        category_sums[tx.category_id] += val
            
            # Categories that now have 0 spent but had a rollup record for this year
            existing_rollups = CategoryRollup.objects.filter(user=user, year=year, month_number=None)
            existing_cat_ids = set(existing_rollups.values_list('category_id', flat=True))
            
            all_involved_cat_ids = existing_cat_ids | set(category_sums.keys())
            
            for category_id in all_involved_cat_ids:
                total_spent = category_sums.get(category_id, Decimal('0.00'))
                CategoryRollup.objects.update_or_create(
                    user=user,
                    category_id=category_id,
                    year=year,
                    month_number=None,
                    defaults={'total_spent': total_spent}
                )

    @staticmethod
    def update_all_rollups(user: User, years_months: Iterable[Tuple[int, int | None]]) -> None:
        """Updates both rollup tables and clears the dirty flag for the user."""
        RollupService.update_user_rollup(user, years_months)
        RollupService.update_category_rollup(user, years_months)

        if hasattr(user, 'profile'):
            profile = user.profile
            profile.needs_rollup_recomputation = False
            profile.save()
