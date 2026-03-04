import pytest
import datetime
from django.urls import reverse
from django.utils import timezone
from api.models import MonthlyBudget, Category, Transaction
from django.contrib.auth.models import User
from api.services.forecasts.forecast_service import ForecastService

@pytest.mark.django_db
def test_current_month_budget_auto_computed_in_list(client):
    # Setup user
    user = User.objects.create_user(username='autouser', password='password')
    client.login(username='autouser', password='password')
    
    # Setup category and some transactions to allow forecasting
    cat = Category.objects.create(name='Food', user=user)
    
    today = timezone.now().date()
    # Create some historical transactions
    for i in range(1, 4):
        month = (today.replace(day=1) - datetime.timedelta(days=30*i)).replace(day=1)
        Transaction.objects.create(
            user=user,
            category=cat,
            amount=100.00,
            transaction_date=month,
            transaction_type='expense',
            status='categorized'
        )
    
    # Ensure no budget exists for current month
    current_month_date = today.replace(day=1)
    assert not MonthlyBudget.objects.filter(user=user, month=current_month_date).exists()
    
    # Access the list view for the current year
    response = client.get(reverse('budget_forecast_list') + f'?year={today.year}')
    
    assert response.status_code == 200
    
    # Verify that the budget was computed
    assert MonthlyBudget.objects.filter(user=user, month=current_month_date).exists()
    
    # Check context
    assert response.context['current_month_budget'] is not None
    assert response.context['current_month_budget'].month == current_month_date
    assert len(response.context['current_month_budget'].top_categories) > 0

@pytest.mark.django_db
def test_current_month_budget_auto_computed_in_detail(client):
    # Setup user
    user = User.objects.create_user(username='autodetail', password='password')
    client.login(username='autodetail', password='password')
    
    # Setup category and some transactions
    cat = Category.objects.create(name='Rent', user=user)
    today = timezone.now().date()
    for i in range(1, 4):
        month = (today.replace(day=1) - datetime.timedelta(days=30*i)).replace(day=1)
        Transaction.objects.create(
            user=user,
            category=cat,
            amount=1000.00,
            transaction_date=month,
            transaction_type='expense',
            status='categorized'
        )
    
    # Ensure no budget exists for current month
    current_month_date = today.replace(day=1)
    assert not MonthlyBudget.objects.filter(user=user, month=current_month_date).exists()
    
    # Access the detail view for the current month
    url = reverse('budget_forecast_detail', kwargs={'year': today.year, 'month': today.month})
    response = client.get(url)
    
    assert response.status_code == 200
    
    # Verify that the budget was computed
    assert MonthlyBudget.objects.filter(user=user, month=current_month_date).exists()
    assert len(response.context['forecasts']) > 0

@pytest.mark.django_db
def test_all_months_auto_computed_in_list(client):
    """Test that all months from Jan to now are auto-computed if missing"""
    # Setup user
    user = User.objects.create_user(username='autoall', password='password')
    client.login(username='autoall', password='password')
    
    # Setup category and some transactions
    cat = Category.objects.create(name='Groceries', user=user)
    
    today = timezone.now().date()
    # Ensure current date is at least March to test multiple months
    # Current local date is 2026-03-02
    
    # Create historical transactions to allow forecasting
    for i in range(1, 6):
        month = (today.replace(day=1) - datetime.timedelta(days=30*i)).replace(day=1)
        Transaction.objects.create(
            user=user,
            category=cat,
            amount=200.00,
            transaction_date=month,
            transaction_type='expense',
            status='categorized'
        )
    
    # Ensure no budgets exist for any month in 2026
    MonthlyBudget.objects.filter(user=user, month__year=2026).delete()
    
    # Access the list view for 2026
    response = client.get(reverse('budget_forecast_list') + '?year=2026')
    
    assert response.status_code == 200
    
    # If today is 2026-03-02, max_month should be 4 (April)
    # Months 1, 2, 3 should be computed. 
    # Month 4 should NOT be computed because it's > 15 days away.
    for m in range(1, 4):
        target_date = datetime.date(2026, m, 1)
        assert MonthlyBudget.objects.filter(user=user, month=target_date).exists(), f"Budget for month {m} was not computed"
    
    april_date = datetime.date(2026, 4, 1)
    # Budget for April should now be initialized with 0 even if AI forecast was skipped
    april_budget = MonthlyBudget.objects.filter(user=user, month=april_date).first()
    assert april_budget is not None, "Budget for April was not initialized"
    assert float(april_budget.planned_amount) == 0.0, "Budget for April should have 0 planned amount (threshold)"
