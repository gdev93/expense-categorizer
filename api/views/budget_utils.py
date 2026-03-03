import datetime
from dataclasses import dataclass, asdict
from typing import Any

from django.contrib import messages
from django.http import HttpResponse, HttpRequest
from django.template.loader import render_to_string

from api.services import BudgetService

from api.models import MonthlyBudget

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
class BudgetForecastDetailContext:
    """Context data for budget forecast detail view"""
    forecasts: list[MonthlyBudget]
    next_month: datetime.date
    total_planned: float
    total_spent: float
    spent_percentage: float
    forecast_available: bool = True

    def to_context(self) -> dict[str, Any]:
        return asdict(self)

def render_budget_htmx_response(request: HttpRequest, year: int, month: int, include_messages: bool = False) -> HttpResponse:
    """
    Centralized helper to render the HTMX response for budget views,
    returning multiple partials (list, summary, main card, and optionally messages).
    """
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
                                    {**summary_context.to_context(), 'hx_oob': True},
                                    request=request)

    # Render the main card
    main_card_html = render_to_string('budget/components/budget-main-card.html',
                                      {**summary_context.to_context(), 'hx_oob': True},
                                      request=request)

    response_html = list_html + summary_html + main_card_html

    if include_messages:
        # Render the messages partial which has hx-swap-oob="true"
        messages_html = render_to_string('components/messages.html', {
            'messages': messages.get_messages(request),
            'hx_oob': True
        }, request=request)
        response_html += messages_html

    return HttpResponse(response_html)
