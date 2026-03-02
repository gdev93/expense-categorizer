import datetime

from django.utils import timezone


def get_next_month_date():
    """Helper to centralize date logic."""
    today = timezone.now().date()
    # Using a more robust date logic:
    return (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
