import datetime
from typing import Any
from django.shortcuts import redirect
from django.views.generic import ListView
from api.models import MonthlyBudget
from api.services.budgets.budget_service import BudgetService
from api.services.data_refresh.data_refresh_service import DataRefreshService
from .utils import render_budget_htmx_response, BudgetForecastDetailContext

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
