from dataclasses import dataclass
from datetime import date
from collections import defaultdict

from django.core.exceptions import BadRequest
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from api.context_processors import available_years_context
from api.models import Transaction, MonthlySummary, CategoryMonthlySummary


@dataclass
class MonthSummary:
    month_number: int
    display_name: str
    date: date  # first day of the month
    total_spending: float
    total_income: float
    total_savings: float
    is_current: bool = False


class MonthlySummerView(View):

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        # Get all years with categorized transactions for the current user
        # Default year: current year if it has data,
        # otherwise the latest year with data (or current year if none)
        available_years = available_years_context(request)['available_years']
        today = timezone.now().date()
        default_year = (
            today.year
            if today.year in available_years
            else (available_years[0] if available_years else today.year)
        )

        # Selected year from query string (check both 'year' and 'selected_year')
        try:
            year_param = request.GET.get("selected_year") or request.GET.get("year")
            selected_year = int(year_param) if year_param else default_year
        except (TypeError, ValueError):
            raise BadRequest("Invalid year format.")

        # Selected month from query string (defaults to current month)
        try:
            month_param = request.GET.get("month") or request.GET.get("selected_month")
            selected_month = int(month_param) if month_param else None
        except (TypeError, ValueError):
            raise BadRequest("Invalid month format.")

        last_transaction = Transaction.objects.filter(user=request.user, status='categorized').order_by('-transaction_date').first()
        last_transaction_date = last_transaction.transaction_date if last_transaction else today
        if selected_month is None:
            selected_month = last_transaction_date.month

        monthly_summary_by_user = MonthlySummary.objects.filter(user_id=request.user.id, year=selected_year)
        # Build month summaries by iterating through transactions
        month_data = defaultdict(lambda: {"spending": 0.0, "income": 0.0})

        for summary in monthly_summary_by_user:
            month_number = summary.month
            amount = float(summary.total_amount or 0)

            if summary.transaction_type == "expense":
                month_data[month_number]["spending"] += amount
            elif summary.transaction_type == "income":
                month_data[month_number]["income"] += amount

        # Convert to MonthSummary objects
        months: list[MonthSummary] = []
        for month_number, data in month_data.items():
            month_date = date(selected_year, int(month_number), 1)
            display_name = month_date.strftime("%B")

            spending = data["spending"]
            income = data["income"]
            savings = income - spending

            # Mark the selected month as current (or actual current month if none selected)
            is_current = (month_number == selected_month)

            months.append(
                MonthSummary(
                    month_number=month_number,
                    display_name=display_name,
                    date=month_date,
                    total_spending=round(spending, 2),
                    total_income=round(income, 2),
                    total_savings=round(savings, 2),
                    is_current=is_current,
                )
            )

        # Sort by month number descending (Dec..Jan) with current month first
        months.sort(key=lambda m: (
            not m.is_current,  # Current month first
            -m.month_number  # Rest in descending order
        ))
        if not months:
            final_selected_month_number = None
        else:
            final_selected_month_number = next((month.month_number for month in months if month.is_current), selected_month)
            if final_selected_month_number not in [month.month_number for month in months]:
                final_selected_month_number = months[0].month_number if months else None
                months[0].is_current = True

        category_monthly_summaries = CategoryMonthlySummary.objects.filter(user_id=request.user.id, year=selected_year)
        if final_selected_month_number:
            category_monthly_summaries = category_monthly_summaries.filter(month=final_selected_month_number)

        context = {
            "year": selected_year,
            "month": final_selected_month_number,
            "selected_month_number": final_selected_month_number,
            "months": months,
            "category_monthly_summaries": category_monthly_summaries
        }

        return render(
            request=request,
            template_name="summary/summary-monthly.html",
            context=context,
        )