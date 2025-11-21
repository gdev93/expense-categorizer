from datetime import datetime
from django.db.models import Sum
from api.models import Transaction


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