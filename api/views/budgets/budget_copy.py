from typing import Any
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View
from api.services.budgets.budget_service import BudgetService
from .utils import render_budget_htmx_response

class BudgetCopyView(View):
    """View to copy a budget from the previous month"""

    def post(self, request, year: int, month: int, *args: Any, **kwargs: Any) -> HttpResponse:
        copied = BudgetService.copy_budget_from_previous_month(request.user, year, month)

        if not copied:
            messages.info(request, "Nessun budget trovato per il mese scorso. È stata applicata la previsione automatica.")

        if request.headers.get('HX-Request'):
            return render_budget_htmx_response(request, year, month, include_messages=True)

        return redirect('budget_forecast_detail', year=year, month=month)
