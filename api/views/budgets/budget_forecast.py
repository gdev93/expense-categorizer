from typing import Any
from django.views.generic import ListView
from api.models import MonthlyBudget
from api.services.budgets.budget_service import BudgetService
from api.utils import get_next_month_date
from .utils import BudgetForecastDetailContext

class BudgetForecastView(ListView):
    """View to display monthly budget forecasts"""
    model = MonthlyBudget
    template_name = 'budget/forecast.html'
    context_object_name = 'forecasts'

    def get_budget_data(self):
        """Fetch data from service, caching it for the duration of the request."""
        if not hasattr(self, '_budget_data') or self._budget_data is None:
            target_date = get_next_month_date()
            self._budget_data = BudgetService.get_monthly_budgets_for_user(
                self.request.user, target_date.year, target_date.month
            )
        return self._budget_data

    def get_queryset(self) -> Any:
        # Just return the forecasts from the service data
        return self.get_budget_data().forecasts

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        budget_data = self.get_budget_data()
        next_month_date = get_next_month_date()

        # Calculate percentage with safe division
        planned = budget_data.total_planned
        spent = budget_data.total_spent
        spent_percentage = (spent / planned * 100) if planned > 0 else 0

        budget_context = BudgetForecastDetailContext(
            forecasts=list(context['forecasts']),
            next_month=next_month_date,
            total_planned=planned,
            total_spent=spent,
            spent_percentage=spent_percentage,
            forecast_available=budget_data.forecast_available
        )

        context.update(budget_context.to_context())
        return context
