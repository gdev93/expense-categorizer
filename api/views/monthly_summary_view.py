from dataclasses import dataclass
from datetime import date
from collections import defaultdict

from django.core.paginator import Paginator
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


class MonthlySummerView(View):

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

        # Selected year from query string (check both 'year' and 'selected_year')
        try:
            selected_year = int(
                request.GET.get("selected_year") or request.GET.get("year", default_year)
            )
        except (TypeError, ValueError):
            selected_year = default_year

        # Selected month from query string (defaults to current month)
        try:
            selected_month = request.GET.get("selected_month")
            selected_month = int(selected_month) if selected_month else None
        except (TypeError, ValueError):
            selected_month = None

        last_transaction = Transaction.objects.filter(user=request.user, status='categorized').order_by('-transaction_date').first()
        last_transaction_date = last_transaction.transaction_date if last_transaction else today
        if selected_month is None:
            selected_month = last_transaction_date.month
        # Fetch all categorized transactions for the selected year
        transactions = Transaction.objects.filter(
            user=request.user,
            status="categorized",
            transaction_date__isnull=False,
            transaction_date__year=selected_year,
            transaction_date__month=selected_month
        ).select_related("category").order_by("-transaction_date")

        # Build month summaries by iterating through transactions
        month_data = defaultdict(lambda: {"spending": 0.0, "income": 0.0})

        for transaction in transactions:
            month_number = transaction.transaction_date.month
            amount = float(transaction.amount or 0)

            if transaction.transaction_type == "expense":
                month_data[month_number]["spending"] += amount
            elif transaction.transaction_type == "income":
                month_data[month_number]["income"] += amount

        # Convert to MonthSummary objects
        months: list[MonthSummary] = []
        for month_number, data in month_data.items():
            month_date = date(selected_year, month_number, 1)
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

        # Fetch and paginate transactions for the selected month
        if final_selected_month_number:
            month_transactions = transactions.filter(
                transaction_date__month=final_selected_month_number
            )

            expenses = month_transactions.filter(transaction_type="expense")
            income = month_transactions.filter(transaction_type="income")

            # Pagination (10 items per page, adjustable)
            expense_paginator = Paginator(expenses, 7)
            income_paginator = Paginator(income, 7)

            expense_page = request.GET.get('expense_page', 1)
            income_page = request.GET.get('income_page', 1)

            paginated_expenses = expense_paginator.get_page(expense_page)
            paginated_income = income_paginator.get_page(income_page)
        else:
            paginated_expenses = None
            paginated_income = None

        context = {
            "available_years": available_years,
            "selected_year": selected_year,
            "selected_month_number": final_selected_month_number,
            "months": months,
            "expenses": paginated_expenses,
            "income": paginated_income,
        }

        return render(
            request=request,
            template_name="summary/summary-monthly.html",
            context=context,
        )