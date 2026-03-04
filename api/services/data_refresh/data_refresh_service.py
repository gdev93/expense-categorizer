import datetime
from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.utils import timezone

from api.models import Transaction
from api.services.rollups.rollup_service import RollupService
from api.services.forecasts.forecast_service import ForecastService

class DataRefreshService:
    """Service to handle refreshing calculations like rollups and forecasts together."""

    @staticmethod
    def trigger_recomputation(user: User, start_date: datetime.date | None = None,
                              categories: set[int] | None = None, force_reset: bool = False) -> None:
        """
        Triggers a full recomputation of rollups and forecasts for a user.
        If start_date is provided, recomputes from that date up to the current month.
        Otherwise, recomputes for all history.
        """
        today = timezone.now().date()
        end_date = today.replace(day=1)

        if start_date:
            # Normalize to the first day of the month
            current_step = start_date.replace(day=1)
            final_years_months = {(current_step.year, current_step.month)}
            # Fill the gap from start_date month up to current month if start_date is in the past
            while current_step < end_date:
                current_step += relativedelta(months=1)
                final_years_months.add((current_step.year, current_step.month))
        else:
            # Get all years/months with transactions for this user
            years_months = Transaction.objects.filter(user=user).values_list(
                'transaction_date__year',
                'transaction_date__month'
            ).distinct()
            final_years_months = set((y, m) for y, m in years_months if y is not None)

        if final_years_months:
            RollupService.update_all_rollups(user, final_years_months)
            ForecastService.compute_forecast(user=user, years_months=final_years_months,
                                             categories=categories, force_reset=force_reset)
