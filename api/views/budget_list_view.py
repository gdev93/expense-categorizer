import datetime
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.generic import ListView

from api.models import MonthlyBudget, YearlyMonthlyUserRollup, CategoryRollup
from api.services import ForecastService, TransactionAggregationService, BudgetService
from api.config import ForecastConfig


@dataclass
class BudgetForecastDetailContext:
    """Context data for budget forecast detail view"""
    forecasts: list[MonthlyBudget]
    target_month: datetime.date
    total_planned: float
    total_spent: float
    spent_percentage: float

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
        categories = [category_id] if category_id else None
        ForecastService.compute_forecast(user=self.request.user, months=[month], years=[year], categories=categories, force_reset=True)
        
        if request.headers.get('HX-Request'):
            result = BudgetService.get_monthly_budgets_for_user(
                self.request.user, year, month
            )
            
            # Context for list
            list_html = render_to_string('budget/components/forecast_list.html', {
                'forecasts': result.forecasts
            }, request=request)
            
            # Context for summary (OOB)
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
            
            # Context for main card (OOB)
            main_card_html = render_to_string('budget/components/budget-main-card.html', {
                'total_planned': result.total_planned,
                'total_spent': result.total_spent,
                'spent_percentage': spent_percentage
            }, request=request)
            
            return HttpResponse(list_html + summary_html + main_card_html)
            
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
            target_month=target_date,
            total_planned=self.result.total_planned,
            total_spent=self.result.total_spent,
            spent_percentage=spent_percentage
        )
        
        context.update(detail_context.to_context())
        context['next_month'] = target_date 
        return context
