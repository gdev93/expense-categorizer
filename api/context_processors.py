from datetime import datetime

from django.db.models import Sum
from django.http import HttpRequest
from django.core.exceptions import PermissionDenied

from api.models import Transaction, Profile, UploadFile
from api.constants import ITALIAN_MONTHS

def available_years_context(request: HttpRequest):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
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
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'available_months': [],
        }

    # Determine target year using a consistent fallback
    # Check GET first, then Session, then fallback
    selected_year_str = request.GET.get('year') or request.session.get('filter_year')
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
        selected_year = last_t.transaction_date.year if last_t and last_t.transaction_date else datetime.now().year

    # Gather distinct months for the selected year
    dates = (Transaction.objects.filter(
        user=request.user,
        status="categorized",
        transaction_date__year=selected_year,
    ).values_list("transaction_date__month", flat=True).distinct().order_by("-transaction_date__month"))

    available_months = [
        {
            'value': str(d),  # month number as string value
            'month_number': d,
            'label_it': f"{ITALIAN_MONTHS[d]}",
        }
        for d in dates
    ]
    return {
        'available_months': available_months
    }

def is_free_trial(request:HttpRequest):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'is_free_trial': False
        }
    user_profile = Profile.objects.filter(user=request.user).first()
    return {
        'is_free_trial': 'free_trial' == user_profile.subscription_type if user_profile else False
    }

def user_uploads(request:HttpRequest):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'user_uploads': []
        }
    return {
        'user_uploads': UploadFile.objects.filter(user=request.user).order_by('-upload_date')
    }

def onboarding_status(request):
    """
    Check and advance onboarding step based on existing data.
    """
    return {}