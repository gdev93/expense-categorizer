import datetime
from dataclasses import dataclass, asdict
from typing import Any

from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import ListView

from api.models import MonthlyBudget
from api.services import BudgetService, DataRefreshService


from .budget_utils import render_budget_htmx_response, BudgetForecastDetailContext


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

class BudgetForecastDetailView(ListView):
    """View to display detailed budget forecasts for a specific month"""
    model = MonthlyBudget
    template_name = 'budget/forecast_detail.html'
    context_object_name = 'forecasts'

    def post(self, request, year, month, *args, **kwargs):
        category_id = request.POST.get('category_id')
        categories = {int(category_id)} if category_id else None
        start_date = datetime.date(year, month, 1)
        DataRefreshService.trigger_recomputation(self.request.user, start_date=start_date, categories=categories, force_reset=True)
        
        if request.headers.get('HX-Request'):
            return render_budget_htmx_response(request, year, month)
            
        return redirect('budget_forecast_detail', year=year, month=month)

    def get_queryset(self) -> Any:
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        
        self.result = BudgetService.get_monthly_budgets_for_user(self.request.user, year, month)
        return self.result.forecasts

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        forecasts = list(context['forecasts'])
        
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        target_date = datetime.date(year, month, 1)
        
        spent_percentage = (self.result.total_spent / self.result.total_planned * 100) if self.result.total_planned > 0 else 0
        detail_context = BudgetForecastDetailContext(
            forecasts=forecasts,
            next_month=target_date,
            total_planned=self.result.total_planned,
            total_spent=self.result.total_spent,
            spent_percentage=spent_percentage,
            forecast_available=self.result.forecast_available
        )
        
        context.update(detail_context.to_context())
        return context
