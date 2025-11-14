from dataclasses import dataclass
from datetime import date
from collections import defaultdict

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from api.models import Transaction


@dataclass
class MonthSummary:
    month_number: int
    display_name: str
    date: date  # first day of the month
    total_spending: float
    total_income: float
    total_savings: float
    is_current: bool = False
    is_previous: bool = False


class SummaryView(View):

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        # Get all years with categorized transactions for the current user
        available_years = list(
            Transaction.objects.filter(
                user=request.user,
                status="categorized",
                transaction_date__isnull=False,
            )
            .values_list("transaction_date__year", flat=True)
            .distinct()
            .order_by("-transaction_date__year")
        )

        # Default year: current year if it has data,
        # otherwise the latest year with data (or current year if none)
        today = timezone.now().date()
        default_year = (
            today.year
            if today.year in available_years
            else (available_years[0] if available_years else today.year)
        )

        # Selected year from query string
        try:
            selected_year = int(request.GET.get("year", default_year))
        except (TypeError, ValueError):
            selected_year = default_year

        # Fetch all categorized transactions for the selected year
        transactions = Transaction.objects.filter(
            user=request.user,
            status="categorized",
            transaction_date__isnull=False,
            transaction_date__year=selected_year,
        ).select_related("category")

        # Build month summaries by iterating through transactions
        month_data = defaultdict(lambda: {"spending": 0.0, "income": 0.0})

        for transaction in transactions:
            month_number = transaction.transaction_date.month
            amount = float(transaction.amount or 0)

            if transaction.transaction_type == "expense":
                month_data[month_number]["spending"] += amount
            elif transaction.transaction_type == "income":
                month_data[month_number]["income"] += amount

        # Determine current and previous month
        current_month = today.month
        current_year = today.year

        # Calculate previous month
        if current_month == 1:
            previous_month = 12
            previous_year = current_year - 1
        else:
            previous_month = current_month - 1
            previous_year = current_year

        # Convert to MonthSummary objects
        months: list[MonthSummary] = []
        for month_number, data in month_data.items():
            month_date = date(selected_year, month_number, 1)
            display_name = month_date.strftime("%B")

            spending = data["spending"]
            income = data["income"]
            savings = income - spending

            # Determine if this is current or previous month
            is_current = (month_number == current_month and selected_year == current_year)
            is_previous = (month_number == previous_month and selected_year == previous_year)

            months.append(
                MonthSummary(
                    month_number=month_number,
                    display_name=display_name,
                    date=month_date,
                    total_spending=round(spending, 2),
                    total_income=round(income, 2),
                    total_savings=round(savings, 2),
                    is_current=is_current,
                    is_previous=is_previous,
                )
            )

        # Sort by month number descending (Dec..Jan) to show recent months first
        # But keep current and previous at the top
        months.sort(key=lambda m: (
            not m.is_current,  # Current month first
            not m.is_previous,  # Previous month second
            -m.month_number  # Rest in descending order
        ))

        context = {
            "available_years": available_years,
            "selected_year": selected_year,
            "months": months,
        }

        return render(
            request=request,
            template_name="summary/summary.html",
            context=context,
        )