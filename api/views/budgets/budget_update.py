from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from api.models import MonthlyBudget
from api.services.budgets.budget_service import BudgetService
from .utils import render_budget_htmx_response

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
