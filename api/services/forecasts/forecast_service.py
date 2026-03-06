import datetime
import logging
from django.contrib.auth.models import User
from django.utils import timezone

from api.config import ForecastConfig
from api.models import Transaction, MonthlyBudget, Category
from processors.stats import ForecastInput, compute_forecast as forecast

logger = logging.getLogger(__name__)

class ForecastService:
    """Service to handle statistical analysis and forecasting."""
    @staticmethod
    def compute_forecast(years_months: set[tuple[int, int]] | None = None, user: User | None = None,
                         categories: set[int] | set[int] | None = None, force_reset: bool = False):
        """
        Compute forecasts for the specified months and years and user.
        :param years_months: list of (year, month) tuples to compute forecasts for
        :param user: target user, if None, then all users are considered
        :param categories: optional list of category ids to filter by
        :param force_reset: if True, overwrites manual budgets and resets user_amount
        :return:
        """
        # 2. Batch users to save memory
        if not user:
            logger.info("No user provided. Computing forecasts for all users.")
        else:
            logger.info(f"Computing forecasts for user: {user.username}")
        user_iterator = User.objects.all().iterator(chunk_size=50) if not user else User.objects.filter(
            id=user.id).iterator()
        target_dates = []
        today = timezone.now().date()
        first_transaction = Transaction.objects.filter(user=user).order_by('transaction_date').first()
        if not first_transaction:
            logger.warning(f"No transactions found for user {user}. Skipping forecast generation.")
            return
        if years_months is None:
            years_months_list = []
            if not first_transaction or not first_transaction.transaction_date:
                logger.info("No transactions found for user. Skipping forecast generation.")
                return
            start_date = first_transaction.transaction_date
            years_to_iterate = list(range(start_date.year, today.year + 1))

            for year in years_to_iterate:
                first_day_of_year = datetime.date(year, 1, 1)
                if year == today.year:
                    months_to_iterate = list(range(first_day_of_year.month, today.month + 1))
                else:
                    months_to_iterate = list(range(first_day_of_year.month, 13))
                for month in months_to_iterate:
                    years_months_list.append((year, month))
            years_months = set(years_months_list)

        for year, month in years_months:
            target_date = datetime.date(year, month, 1)
            target_dates.append((target_date, first_transaction.transaction_date))

        for user in user_iterator:
            logger.info(f"Processing user: {user.username} for target dates {target_dates}")
            categories_to_process = Category.objects.filter(user=user)
            if categories:
                categories_to_process = categories_to_process.filter(id__in=categories)
            for category in categories_to_process:
                for target_date, period_start in target_dates:
                    # 1. Setup timing (Target: Next month, first day)
                    # Find first day of next month
                    if not force_reset and target_date > today and (
                            target_date - today).days > ForecastConfig.FORECAST_THRESHOLD_DAYS:
                        logger.info(f"Skipping AI forecast for {target_date} as it is more than {ForecastConfig.FORECAST_THRESHOLD_DAYS} days away. Initializing with 0 if missing.")
                        # Ensure record exists even if skipped for AI, to allow manual planning
                        if not MonthlyBudget.objects.filter(user=user, category=category, month=target_date).exists():
                             MonthlyBudget.objects.create(
                                user=user,
                                category=category,
                                month=target_date,
                                planned_amount=0,
                                is_automated=True,
                                user_amount=None
                             )
                        continue
                    logger.info(
                        f"Generating forecasts for {target_date} for user: {user.username} and category: {category.name}. Considering transactions from {period_start}")
                    transactions = Transaction.objects.filter(
                        user=user,
                        category=category,
                        transaction_date__gte=period_start,
                        transaction_date__lte=target_date
                    )

                    forecast_inputs = [
                        ForecastInput(date=datetime.date(tx.transaction_date.year, tx.transaction_date.month, 1), amount=float(tx.amount))
                        for tx in transactions
                    ]
                    logger.info(f"Generating forecast for {category.name}")
                    final_forecast = forecast(forecast_inputs)
                    # Check if a manual budget already exists
                    existing_budget = MonthlyBudget.objects.filter(
                        user=user,
                        category=category,
                        month=target_date
                    ).first()

                    if not force_reset and existing_budget and not existing_budget.is_automated:
                        logger.info(f"Skipping manual budget for {category.name} in {target_date}")
                        continue
                    if force_reset:
                        existing_budget.planned_amount = final_forecast
                        existing_budget.is_automated = True
                        existing_budget.user_amount = None
                        existing_budget.save()

                    else:
                        monthly_budget = MonthlyBudget.objects.filter(
                            user=user,
                            category=category,
                            month=target_date
                        ).first()
                        if not monthly_budget:
                            MonthlyBudget.objects.create(
                                user=user,
                                category=category,
                                month=target_date,
                                planned_amount=final_forecast,
                                is_automated=True,
                                user_amount=None
                            )
                        else:
                            monthly_budget.planned_amount = final_forecast
                            monthly_budget.is_automated = monthly_budget.user_amount is None
                            monthly_budget.save()


            logger.info(f"User: {user.username} completed")
