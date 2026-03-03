import datetime
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from functools import wraps
from typing import Iterable, Dict, Tuple, Any, List

from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.utils import timezone

from api.config import ForecastConfig
from api.models import Transaction, Merchant, YearlyMonthlyUserRollup, MonthlyBudget, Category, CategoryRollup
from api.privacy_utils import generate_blind_index, generate_encrypted_trigrams
from processors.stats import ForecastInput, compute_forecast

logger = logging.getLogger(__name__)

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
            curr_budget.user_amount = prev_budget.final_amount
            curr_budget.planned_amount = prev_budget.planned_amount
            curr_budget.is_automated = prev_budget.is_automated
            curr_budget.save()

        return True


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


class MerchantService:

    @staticmethod
    def get_merchants_candidates(search_term: str, user: User, max_results: int) -> list[Merchant]:
        hashed_user_input = generate_blind_index(search_term)
        merchants_from_db = Merchant.objects.filter(name_hash=hashed_user_input, user=user)
        exact_match = merchants_from_db.first()
        if exact_match:
            return [exact_match]
        hashed_user_input = generate_encrypted_trigrams(search_term)
        merchants_from_db = Merchant.objects.filter(fuzzy_search_trigrams__overlap=hashed_user_input,
                                                    user=user)
        results = []
        source_counter = Counter(hashed_user_input)
        for merchant in merchants_from_db:
            additional_weight = 1 if search_term.lower() in merchant.name.lower() else 0
            results.append(
                (merchant, sum(source_counter[tg] for tg in merchant.fuzzy_search_trigrams) + additional_weight))
        best_results = sorted(results, key=lambda x: x[1], reverse=True)[:max_results]
        return [best_merchant for best_merchant, _ in best_results]


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

        if years_months is None:
            years_months = []

            first_transaction = Transaction.objects.filter(user=user).order_by('transaction_date').first()
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
                    years_months.append((year, month))

        for year, month in years_months:
            target_date = datetime.date(year, month, 1)
            period_start = target_date - datetime.timedelta(days=ForecastConfig.get_history_days())
            target_dates.append((target_date, period_start))

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
                    grouped_data = {}
                    for tx in transactions:
                        key = (tx.transaction_date.year, tx.transaction_date.month)
                        if key not in grouped_data:
                            grouped_data[key] = 0
                        grouped_data[key] += tx.amount

                    forecast_inputs = [
                        ForecastInput(date=datetime.date(y, m, 1), amount=float(amount))
                        for (y, m), amount in grouped_data.items()
                    ]
                    logger.info(f"Generating forecast for {category.name}")
                    
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
                        MonthlyBudget.objects.update_or_create(
                            user=user,
                            category=category,
                            month=target_date,
                            defaults={
                                'planned_amount': compute_forecast(forecast_inputs),
                                'is_automated': True,
                                'user_amount': None
                            }
                        )
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
                                planned_amount=compute_forecast(forecast_inputs),
                                is_automated=True,
                                user_amount=None
                            )
                        else:
                            monthly_budget.planned_amount = compute_forecast(forecast_inputs)
                            monthly_budget.is_automated = monthly_budget.user_amount is None
                            monthly_budget.save()


            logger.info(f"User: {user.username} completed")


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
