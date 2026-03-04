from typing import Any
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View
from api.services.budgets.budget_service import BudgetService
from .utils import render_budget_htmx_response

class BudgetResetView(View):
    """View to reset all monthly budgets to automated values"""

    def post(self, request, year: int, month: int, *args: Any, **kwargs: Any) -> HttpResponse:
        BudgetService.reset_monthly_budgets(request.user, year, month)

        if request.headers.get('HX-Request'):
            return render_budget_htmx_response(request, year, month)

        return redirect('budget_forecast_detail', year=year, month=month)
