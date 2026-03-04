import datetime
from typing import Any
from django.utils import timezone
from django.views.generic import ListView
from api.models import MonthlyBudget
from api.services.budgets.budget_service import BudgetService

class BudgetForecastListView(ListView):
    """View to list months with budget forecasts"""
    model = MonthlyBudget
    template_name = 'budget/forecast_list.html'
    context_object_name = 'months'

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        months = context.get('months', [])

        today = timezone.now().date()
        current_month_date = today.replace(day=1)
        next_month_date = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)

        current_month_budget = None
        next_month_budget = None
        other_months = []

        for item in months:
            if item.month == next_month_date:
                next_month_budget = item
            elif item.month == current_month_date:
                current_month_budget = item
            else:
                other_months.append(item)

        context['year'] = self.selected_year
        context['current_month_budget'] = current_month_budget
        context['next_month_budget'] = next_month_budget
        context['other_months'] = other_months
        return context

    def get_queryset(self) -> Any:
        # Determine target year using a consistent fallback
        selected_year_str = self.request.GET.get('year') or self.request.session.get('filter_year')
        try:
            selected_year = int(selected_year_str) if selected_year_str else None
        except (TypeError, ValueError):
            selected_year = None

        result = BudgetService.get_budget_list_for_user(self.request.user, selected_year)
        self.selected_year = result.year
        return result.months
