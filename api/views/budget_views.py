import datetime
from dataclasses import dataclass, asdict
from typing import Any

from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView

from api.models import MonthlyBudget
from api.services import BudgetService
from api.utils import get_next_month_date


from .budget_utils import render_budget_htmx_response, BudgetForecastDetailContext


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


class BudgetUpdateView(View):
    """View to update monthly budget amount"""

    def post(self, request, pk, *args, **kwargs):
        try:
            amount_str = request.POST.get('amount')
            if amount_str is None:
                return JsonResponse({'status': 'error', 'message': 'Missing amount'}, status=400)
                
            amount = float(amount_str.replace(',', '.'))
            budget = BudgetService.update_monthly_budget(request.user, pk, amount)
            
            if request.headers.get('HX-Request'):
                return render_budget_htmx_response(
                    request, budget.month.year, budget.month.month
                )
            
            return redirect('budget_forecast_detail', year=budget.month.year, month=budget.month.month)
        except (MonthlyBudget.DoesNotExist, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Invalid budget or amount'}, status=400)


class BudgetCopyView(View):
    """View to copy a budget from the previous month"""

    def post(self, request, year: int, month: int, *args: Any, **kwargs: Any) -> HttpResponse:
        copied = BudgetService.copy_budget_from_previous_month(request.user, year, month)

        if not copied:
            messages.info(request, "Nessun budget trovato per il mese scorso. È stata applicata la previsione automatica.")

        if request.headers.get('HX-Request'):
            return render_budget_htmx_response(request, year, month, include_messages=True)

        return redirect('budget_forecast_detail', year=year, month=month)


class BudgetResetView(View):
    """View to reset all monthly budgets to automated values"""

    def post(self, request, year: int, month: int, *args: Any, **kwargs: Any) -> HttpResponse:
        BudgetService.reset_monthly_budgets(request.user, year, month)

        if request.headers.get('HX-Request'):
            return render_budget_htmx_response(request, year, month)

        return redirect('budget_forecast_detail', year=year, month=month)
