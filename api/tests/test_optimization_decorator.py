import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User
from api.models import Transaction, Category, YearlyMonthlyUserRollup
from api.services import TransactionAggregationService
from api.views.transactions.transaction_mixins import TransactionFilterState

@pytest.mark.django_db
class TestOptimizeTotalAmountDecorator:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser_opt", password="password")
        self.category = Category.objects.create(name="Food", user=self.user)
        
        # Create transactions for 2025
        # Jan: 100.00
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 1, 15),
            amount=Decimal("100.00"),
            category=self.category,
            transaction_type='expense',
            status='categorized'
        )
        # Feb: 50.00
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 2, 10),
            amount=Decimal("50.00"),
            category=self.category,
            transaction_type='expense',
            status='categorized'
        )
        
        # Create rollup for 2025
        # Yearly
        YearlyMonthlyUserRollup.objects.create(
            user=self.user,
            by_year=2025,
            month_number=None,
            total_amount_expense_by_year=Decimal("150.00")
        )
        # Monthly Jan
        YearlyMonthlyUserRollup.objects.create(
            user=self.user,
            by_year=2025,
            month_number=1,
            total_amount_expense_by_month=Decimal("100.00")
        )
        # Monthly Feb
        YearlyMonthlyUserRollup.objects.create(
            user=self.user,
            by_year=2025,
            month_number=2,
            total_amount_expense_by_month=Decimal("50.00")
        )

    def test_calculate_total_amount_uses_yearly_rollup(self):
        # Default filters for 2025, no months specified (or empty list)
        filters = TransactionFilterState(year=2025, months=[])
        assert filters.is_default_filter is True
        
        queryset = Transaction.objects.filter(user=self.user, transaction_date__year=2025)
        
        # We can change the rollup value to a distinct one to prove it's being used
        rollup = YearlyMonthlyUserRollup.objects.get(user=self.user, by_year=2025, month_number=None)
        rollup.total_amount_expense_by_year = Decimal("999.99")
        rollup.save()
        
        total = TransactionAggregationService.calculate_total_amount(self.user, filters, queryset)
        
        assert total == Decimal("999.99")

    def test_calculate_total_amount_yearly_with_multiple_rollup_records(self):
        # Ensure that if both monthly and yearly records exist, it picks the yearly one
        filters = TransactionFilterState(year=2025, months=[])
        queryset = Transaction.objects.filter(user=self.user, transaction_date__year=2025)
        
        # Delete and recreate rollup in reverse order
        YearlyMonthlyUserRollup.objects.filter(user=self.user, by_year=2025).delete()
        
        # Create monthly records FIRST
        YearlyMonthlyUserRollup.objects.create(
            user=self.user,
            by_year=2025,
            month_number=1,
            total_amount_expense_by_month=Decimal("100.00")
        )
        # Create yearly record LAST
        YearlyMonthlyUserRollup.objects.create(
            user=self.user,
            by_year=2025,
            month_number=None,
            total_amount_expense_by_year=Decimal("150.00")
        )
        
        total = TransactionAggregationService.calculate_total_amount(self.user, filters, queryset)
        assert total == Decimal("150.00")

    def test_calculate_total_amount_uses_monthly_rollups(self):
        # Default filters for 2025, months Jan and Feb
        filters = TransactionFilterState(year=2025, months=[1, 2])
        assert filters.is_default_filter is True
        
        queryset = Transaction.objects.filter(user=self.user, transaction_date__year=2025, transaction_date__month__in=[1, 2])
        
        # Change monthly rollup values
        rollup_jan = YearlyMonthlyUserRollup.objects.get(user=self.user, by_year=2025, month_number=1)
        rollup_jan.total_amount_expense_by_month = Decimal("1000.00")
        rollup_jan.save()
        
        rollup_feb = YearlyMonthlyUserRollup.objects.get(user=self.user, by_year=2025, month_number=2)
        rollup_feb.total_amount_expense_by_month = Decimal("500.00")
        rollup_feb.save()
        
        total = TransactionAggregationService.calculate_total_amount(self.user, filters, queryset)
        
        assert total == Decimal("1500.00")

    def test_calculate_total_amount_fallbacks_on_non_default_filter(self):
        # Non-default filter (search query)
        filters = TransactionFilterState(year=2025, months=[], search="Something")
        assert filters.is_default_filter is False
        
        queryset = Transaction.objects.filter(user=self.user, transaction_date__year=2025)
        
        # Even if rollup has a different value, it should use the real sum from transactions
        rollup = YearlyMonthlyUserRollup.objects.get(user=self.user, by_year=2025, month_number=None)
        rollup.total_amount_expense_by_year = Decimal("999.99")
        rollup.save()
        
        total = TransactionAggregationService.calculate_total_amount(self.user, filters, queryset)
        
        # Real sum is 100 + 50 = 150
        assert total == Decimal("150.00")

    def test_calculate_total_amount_fallbacks_when_no_rollup_exists(self):
        # Default filters for 2026 (no rollup exists)
        filters = TransactionFilterState(year=2026, months=[])
        assert filters.is_default_filter is True
        
        # Create a transaction for 2026
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2026, 1, 1),
            amount=Decimal("75.00"),
            category=self.category,
            transaction_type='expense',
            status='categorized'
        )
        
        queryset = Transaction.objects.filter(user=self.user, transaction_date__year=2026)
        
        total = TransactionAggregationService.calculate_total_amount(self.user, filters, queryset)
        
        assert total == Decimal("75.00")

    def test_calculate_total_amount_fallbacks_when_no_year_in_filters(self):
        # Default filters but NO year (e.g. year=None or 0)
        filters = TransactionFilterState(year=None, months=[])
        
        queryset = Transaction.objects.filter(user=self.user)
        
        total = TransactionAggregationService.calculate_total_amount(self.user, filters, queryset)
        
        # Should sum all transactions: 100 (Jan 2025) + 50 (Feb 2025) = 150
        assert total == Decimal("150.00")
