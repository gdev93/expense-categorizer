import datetime
from dataclasses import dataclass, asdict
from pyexpat.errors import messages
from typing import Any

from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import ListView

from api.models import MonthlyBudget
from api.services import BudgetService, ForecastService
from api.utils import get_next_month_date


@dataclass
class BudgetForecastContext:
    """Context data for monthly budget forecast view"""
    forecasts: list[MonthlyBudget]
    next_month: datetime.date
    total_planned: float
    total_spent: float
    spent_percentage: float
    forecast_available: bool = True

    def to_context(self) -> dict[str, Any]:
        return asdict(self)



@dataclass
class BudgetSummaryContext:
    """Context data for budget summary component"""
    total_planned: float
    total_spent: float
    spent_percentage: float
    next_month: datetime.date

    def to_context(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BudgetUpdateContext:
    """Context data for monthly budget update view"""
    budget: MonthlyBudget

    def to_context(self) -> dict[str, Any]:
        return asdict(self)


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

        budget_context = BudgetForecastContext(
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
                result = BudgetService.get_monthly_budgets_for_user(
                    request.user, budget.month.year, budget.month.month
                )
                
                # Render the list
                list_html = render_to_string('budget/components/forecast_list.html', {
                    'forecasts': result.forecasts
                }, request=request)

                # Render the summary partial which has hx-swap-oob="true"
                spent_percentage = (result.total_spent / result.total_planned * 100) if result.total_planned > 0 else 0
                summary_context = BudgetSummaryContext(
                    total_planned=result.total_planned,
                    total_spent=result.total_spent,
                    spent_percentage=spent_percentage,
                    next_month=budget.month
                )
                summary_html = render_to_string('budget/components/budget-summary.html', 
                    summary_context.to_context(), 
                    request=request)

                # Render the main card
                main_card_html = render_to_string('budget/components/budget-main-card.html',
                                                  summary_context.to_context(),
                                                  request=request)

                return HttpResponse(list_html + summary_html + main_card_html)
            
            return redirect('budget_forecast_detail', year=budget.month.year, month=budget.month.month)
        except (MonthlyBudget.DoesNotExist, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Invalid budget or amount'}, status=400)


class BudgetCopyView(View):
    """View to copy a budget from the previous month"""

    def post(self, request, year: int, month: int, *args: Any, **kwargs: Any) -> HttpResponse:
        BudgetService.copy_budget_from_previous_month(request.user, year, month)

        if request.headers.get('HX-Request'):
            result = BudgetService.get_monthly_budgets_for_user(
                request.user, year, month
            )

            # Render the list
            list_html = render_to_string('budget/components/forecast_list.html', {
                'forecasts': result.forecasts
            }, request=request)

            # Render the summary partial which has hx-swap-oob="true"
            spent_percentage = (result.total_spent / result.total_planned * 100) if result.total_planned > 0 else 0
            summary_context = BudgetSummaryContext(
                total_planned=result.total_planned,
                total_spent=result.total_spent,
                spent_percentage=spent_percentage,
                next_month=datetime.date(year, month, 1)
            )
            summary_html = render_to_string('budget/components/budget-summary.html',
                                            summary_context.to_context(),
                                            request=request)

            # Render the main card
            main_card_html = render_to_string('budget/components/budget-main-card.html',
                                              summary_context.to_context(),
                                              request=request)

            return HttpResponse(list_html + summary_html + main_card_html)

        return redirect('budget_forecast_detail', year=year, month=month)


class BudgetResetView(View):
    """View to reset all monthly budgets to automated values"""

    def post(self, request, year: int, month: int, *args: Any, **kwargs: Any) -> HttpResponse:
        BudgetService.reset_monthly_budgets(request.user, year, month)

        if request.headers.get('HX-Request'):
            result = BudgetService.get_monthly_budgets_for_user(
                request.user, year, month
            )

            # Render the list
            list_html = render_to_string('budget/components/forecast_list.html', {
                'forecasts': result.forecasts
            }, request=request)

            # Render the summary partial which has hx-swap-oob="true"
            spent_percentage = (result.total_spent / result.total_planned * 100) if result.total_planned > 0 else 0
            summary_context = BudgetSummaryContext(
                total_planned=result.total_planned,
                total_spent=result.total_spent,
                spent_percentage=spent_percentage,
                next_month=datetime.date(year, month, 1)
            )
            summary_html = render_to_string('budget/components/budget-summary.html',
                                            summary_context.to_context(),
                                            request=request)

            # Render the main card
            main_card_html = render_to_string('budget/components/budget-main-card.html',
                                              summary_context.to_context(),
                                              request=request)

            return HttpResponse(list_html + summary_html + main_card_html)

        return redirect('budget_forecast_detail', year=year, month=month)
