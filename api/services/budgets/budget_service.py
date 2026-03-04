import datetime
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Dict, List

from django.contrib.auth.models import User
from django.utils import timezone

from api.config import ForecastConfig
from api.models import MonthlyBudget, CategoryRollup
from api.services.forecasts.forecast_service import ForecastService

@dataclass
class MonthlyBudgetsResult:
    """Result of fetching and enriching monthly budgets."""
    forecasts: list[MonthlyBudget]
    total_planned: float
    total_spent: float
    forecast_available: bool = True

@dataclass
class TopCategory:
    """A simple representation of a category and its planned amount for summaries."""
    name: str
    amount: float

@dataclass
class BudgetMonthSummary:
    """A summary of a month's budget and spending."""
    month: datetime.date
    total_planned: float
    total_spent: float
    top_categories: list[TopCategory]
    forecast_available: bool
    spent_percentage: float | None = None

@dataclass
class BudgetListResult:
    """Result of preparing the monthly budget summary list."""
    months: list[BudgetMonthSummary]
    year: int

class BudgetService:
    """Service to handle budget business logic and data preparation for views."""

    @staticmethod
    def _get_max_month_for_year(year: int) -> int:
        """Determine the maximum month to consider for a given year based on current date."""
        today = timezone.now().date()
        next_month_date = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        
        if year < next_month_date.year:
            return 12
        elif year == next_month_date.year:
            return next_month_date.month
        return 0

    @staticmethod
    def _ensure_forecasts_computed(user: User, year: int, months: int | list[int]) -> None:
        """Compute missing forecasts for a user for specific month(s) in a given year."""
        # Normalize to a list of months
        months_to_check = [months] if isinstance(months, int) else months

        missing_months = [
            m for m in months_to_check
            if not MonthlyBudget.objects.filter(
                user=user,
                month=datetime.date(year, m, 1)
            ).exists()
        ]
        if missing_months:
            years_months = set([(year, m) for m in missing_months])
            ForecastService.compute_forecast(user=user, years_months=years_months)

    @staticmethod
    def enrich_budgets_with_spent_data(user: User, budgets: Iterable[MonthlyBudget]) -> None:
        """Enrich a list of MonthlyBudget objects with spent amount and percentage using CategoryRollup."""
        # 1. Group budgets by month to minimize queries
        budgets_by_month = defaultdict(list)
        for b in budgets:
            budgets_by_month[b.month].append(b)

        for month, month_budgets in budgets_by_month.items():
            category_ids = [b.category_id for b in month_budgets]

            # 2. Fetch rollup records for this month and these categories
            rollups = CategoryRollup.objects.filter(
                user=user,
                year=month.year,
                month_number=month.month,
                category_id__in=category_ids
            )

            spent_sums = {r.category_id: r.total_spent for r in rollups}

            # 3. Attach to budgets
            for b in month_budgets:
                spent = spent_sums.get(b.category_id, Decimal('0.00'))
                b.spent_amount = float(spent) if spent is not None else 0.0
                planned = b.final_amount
                if planned > 0:
                    b.spent_percentage = (b.spent_amount / planned) * 100
                else:
                    b.spent_percentage = 0.0

    @staticmethod
    def get_monthly_budgets_for_user(user: User, year: int, month: int) -> MonthlyBudgetsResult:
        """Fetch, compute (if missing), and enrich monthly budgets with spent data."""
        # Optimization: only compute the forecast for the requested month
        BudgetService._ensure_forecasts_computed(user, year, month)

        target_date = datetime.date(year, month, 1)
        today = timezone.now().date()
        current_month_date = today.replace(day=1)
        is_future = target_date > current_month_date
        forecast_available = True
        if is_future:
            forecast_available = (target_date - today).days <= ForecastConfig.FORECAST_THRESHOLD_DAYS

        forecasts = MonthlyBudget.objects.filter(
            user=user,
            month=target_date
        ).select_related('category').order_by('category__name')

        forecasts_list = list(forecasts)
        BudgetService.enrich_budgets_with_spent_data(user, forecasts_list)
        total_planned = sum(f.final_amount for f in forecasts_list)
        total_spent = sum(f.spent_amount for f in forecasts_list)

        return MonthlyBudgetsResult(
            forecasts=forecasts_list, 
            total_planned=total_planned,
            total_spent=total_spent,
            forecast_available=forecast_available
        )

    @staticmethod
    def get_budget_list_for_user(user: User, year: int | None = None) -> BudgetListResult:
        """Prepare the list of monthly budget summaries for a given year."""
        today = timezone.now().date()
        current_month_date = today.replace(day=1)

        if year is None:
            last_b = MonthlyBudget.objects.filter(user=user).order_by('-month').first()
            year = last_b.month.year if last_b else today.year

        max_month = BudgetService._get_max_month_for_year(year)
        # For the list view, we still want to ensure all relevant months are computed
        BudgetService._ensure_forecasts_computed(user, year, list(range(1, max_month + 1)))

        # Re-fetch all budgets for the year after computation
        all_budgets = MonthlyBudget.objects.filter(
            user=user,
            month__year=year
        ).select_related('category').order_by('-month', 'category__name')

        # Fetch spent amounts from rollups
        spent_rollups = CategoryRollup.objects.filter(
            user=user,
            year=year,
            month_number__isnull=False
        )
        spent_dict = defaultdict(float)
        for r in spent_rollups:
            spent_dict[r.month_number] += float(r.total_spent or 0.0)

        months_dict: Dict[datetime.date, BudgetMonthSummary] = {}
        for m in range(1, max_month + 1):
            target_date = datetime.date(year, m, 1)
            is_future = target_date > current_month_date
            forecast_available = True
            if is_future:
                forecast_available = (target_date - today).days <= ForecastConfig.FORECAST_THRESHOLD_DAYS

            months_dict[target_date] = BudgetMonthSummary(
                month=target_date,
                total_planned=0.0,
                total_spent=spent_dict.get(m, 0.0),
                top_categories=[],
                forecast_available=forecast_available
            )

        for budget in all_budgets:
            month_key = budget.month
            if month_key in months_dict:
                months_dict[month_key].total_planned += budget.final_amount
                months_dict[month_key].top_categories.append(TopCategory(
                    name=budget.category.name,
                    amount=budget.final_amount
                ))

        for month_data in months_dict.values():
            month_data.top_categories = sorted(
                month_data.top_categories,
                key=lambda x: x.amount,
                reverse=True
            )[:4]

            if month_data.total_planned > 0:
                month_data.spent_percentage = (month_data.total_spent / month_data.total_planned) * 100
            else:
                month_data.spent_percentage = None

        sorted_months = sorted(months_dict.values(), key=lambda x: x.month, reverse=True)
        return BudgetListResult(months=sorted_months, year=year)

    @staticmethod
    def update_monthly_budget(user: User, budget_id: int, amount: float) -> MonthlyBudget:
        """Update a specific monthly budget and return it."""
        budget = MonthlyBudget.objects.get(pk=budget_id, user=user)
        budget.user_amount = amount
        budget.is_automated = False
        budget.save()
        return budget

    @staticmethod
    def reset_monthly_budgets(user: User, year: int, month: int) -> None:
        """Reset all monthly budgets for a user and month to their automated values."""
        ForecastService.compute_forecast(user=user, years_months={(year, month)}, force_reset=True)

    @staticmethod
    def copy_budget_from_previous_month(user: User, year: int, month: int) -> bool:
        """Copy budget settings (user_amount, is_automated) from the previous month to the current one."""
        target_month = month - 1 if month > 1 else 12
        target_year = year if month > 1 else year - 1

        # Optimization: only compute the forecast for the requested month
        BudgetService._ensure_forecasts_computed(user, year, month)
        BudgetService._ensure_forecasts_computed(user, target_year, target_month)

        current_monthly_budget_date = datetime.date(year, month, 1)
        previous_monthly_budget_date = datetime.date(target_year, target_month, 1)

        all_previous_category_budgets = MonthlyBudget.objects.filter(
            user=user,
            month=previous_monthly_budget_date
        )

        if not all_previous_category_budgets.exists():
            # If no previous budget available, reset current to forecast
            BudgetService.reset_monthly_budgets(user, year, month)
            return False

        all_current_category_budgets = MonthlyBudget.objects.filter(
            user=user,
            month=current_monthly_budget_date
        )

        for prev_budget in all_previous_category_budgets:
            curr_budget = all_current_category_budgets.filter(category=prev_budget.category).first()
            if not curr_budget:
                curr_budget = MonthlyBudget.objects.create(
                    user=user,
                    category=prev_budget.category,
                    month=current_monthly_budget_date
                )
            curr_budget.user_amount = prev_budget.user_amount if not prev_budget.is_automated else None
            curr_budget.planned_amount = prev_budget.planned_amount
            curr_budget.is_automated = prev_budget.is_automated
            curr_budget.save()

        return True
