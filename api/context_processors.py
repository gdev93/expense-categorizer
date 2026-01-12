from datetime import datetime

from django.db.models import Sum
from django.http import HttpRequest

from api.models import Transaction, Profile, CsvUpload


def savings_context(request):
    """
    Add current year savings data to all templates.
    """
    if not request.user.is_authenticated:
        return {
            'current_year': datetime.now().year,
            'total_savings_by_current_year': 0,
        }

    current_year = datetime.now().year

    # Calculate total income for current year
    total_income = Transaction.objects.filter(
        user=request.user,
        transaction_type='income',
        transaction_date__year=current_year,
        status='categorized'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Calculate total expenses for current year
    total_expenses = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        transaction_date__year=current_year,
        status='categorized'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Savings = Income - Expenses
    total_savings_by_current_year = float(total_income) - float(total_expenses)

    return {
        'current_year': current_year,
        'total_savings_by_current_year': round(total_savings_by_current_year, 2),
    }


def available_years_context(request: HttpRequest):
    if not request.user.is_authenticated:
        return {
            'available_years': []
        }

    # We only get available years here.
    # The 'year' selection logic should primarily stay in the views
    # to ensure consistency with the filtered queryset.
    years = list(
        Transaction.objects.filter(
            user=request.user,
            status="categorized",
            transaction_date__isnull=False,
        )
        .values_list("transaction_date__year", flat=True)
        .distinct()
        .order_by("-transaction_date__year")
    )

    return {
        'available_years': years or [datetime.now().year]
    }


def available_months_context(request):
    """
    Provide a list of available months for the authenticated user as a global context.
    - Months are restricted to the selected year (from GET 'year') or the most recent year with data.
    """
    if not request.user.is_authenticated:
        return {
            'available_months': [],
        }

    # Determine target year using a consistent fallback
    selected_year_str = request.GET.get('year')
    if selected_year_str:
        try:
            selected_year = int(selected_year_str)
        except (TypeError, ValueError):
            selected_year = None
    else:
        selected_year = None

    if selected_year is None:
        # Fallback to the most recent transaction year
        last_t = Transaction.objects.filter(user=request.user, status='categorized').order_by('-transaction_date').first()
        selected_year = last_t.transaction_date.year if last_t else datetime.now().year

    # Gather distinct months for the selected year
    dates = (Transaction.objects.filter(
        user=request.user,
        status="categorized",
        transaction_date__year=selected_year,
    ).values_list("transaction_date__month", flat=True).distinct().order_by("-transaction_date__month"))

    italian_months = {
        1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
        5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
        9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
    }

    available_months = [
        {
            'value': str(d),  # month number as string value
            'month_number': d,
            'label_it': f"{italian_months[d]}",
        }
        for d in dates
    ]
    return {
        'available_months': available_months
    }

def is_free_trial(request:HttpRequest):
    if not request.user.is_authenticated:
        return {
            'is_free_trial': False
        }
    user_profile = Profile.objects.filter(user=request.user).first()
    return {
        'is_free_trial': 'free_trial' == user_profile.subscription_type if user_profile else False
    }

def user_uploads(request:HttpRequest):
    return {
        'user_uploads': CsvUpload.objects.filter(user=request.user).order_by('-upload_date') if request.user.is_authenticated else []
    }