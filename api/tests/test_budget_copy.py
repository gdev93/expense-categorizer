import pytest
from django.urls import reverse
from django.utils import timezone
import datetime
from api.models import MonthlyBudget, Category
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from unittest.mock import patch

@pytest.mark.django_db
def test_budget_copy_view(client):
    # 1. Setup user
    user = User.objects.create_user(username='testuser', password='password')
    client.login(username='testuser', password='password')

    # 2. Setup categories
    cat1 = Category.objects.create(name='Food', user=user)
    cat2 = Category.objects.create(name='Rent', user=user)

    # 3. Setup months
    today = timezone.now().date().replace(day=1)
    previous_month_date = (today - datetime.timedelta(days=1)).replace(day=1)
    current_month_date = today

    # 4. Create budgets for previous month
    MonthlyBudget.objects.create(
        user=user,
        category=cat1,
        month=previous_month_date,
        planned_amount=100.00,
        user_amount=120.00,
        is_automated=False
    )
    MonthlyBudget.objects.create(
        user=user,
        category=cat2,
        month=previous_month_date,
        planned_amount=1000.00,
        is_automated=True
    )

    # 5. Create budgets for current month (with different values)
    MonthlyBudget.objects.create(
        user=user,
        category=cat1,
        month=current_month_date,
        planned_amount=110.00,
        is_automated=True
    )
    # Rent not yet created for current month

    # 6. Call copy view
    url = reverse('budget_copy', kwargs={'year': current_month_date.year, 'month': current_month_date.month})
    response = client.post(url, HTTP_HX_REQUEST='true')

    assert response.status_code == 200

    # 7. Verify results
    # Food should have been updated
    food_budget = MonthlyBudget.objects.get(user=user, category=cat1, month=current_month_date)
    assert float(food_budget.user_amount) == 120.00
    assert food_budget.is_automated is False

    # Rent should have been created
    rent_budget = MonthlyBudget.objects.get(user=user, category=cat2, month=current_month_date)
    assert rent_budget.user_amount is None
    assert rent_budget.is_automated is True

    # Check HTMX response content
    content = response.content.decode()
    assert 'Food' in content
    assert 'Rent' in content
    assert '120.00' in content  # For the input value
    assert '120,00' in content  # For the total planned value


@pytest.mark.django_db
def test_budget_copy_no_previous_month_view(client):
    # 1. Setup user
    user = User.objects.create_user(username='testuser_empty', password='password')
    client.login(username='testuser_empty', password='password')

    # 2. Setup categories
    cat1 = Category.objects.create(name='Food', user=user)

    # 3. Setup months
    today = timezone.now().date().replace(day=1)
    current_month_date = today

    # 4. No budgets for previous month 
    # We mock _ensure_forecasts_computed to do nothing, so no budgets are created
    with patch('api.services.BudgetService._ensure_forecasts_computed') as mock_ensure:
        # We only want to mock it for the previous month call
        
        # 5. Create a manual budget for current month (which should be reset)
        MonthlyBudget.objects.create(
            user=user,
            category=cat1,
            month=current_month_date,
            planned_amount=100.00,
            user_amount=150.00,
            is_automated=False
        )

        # 6. Call copy view
        url = reverse('budget_copy', kwargs={'year': current_month_date.year, 'month': current_month_date.month})
        response = client.post(url, HTTP_HX_REQUEST='true')

    assert response.status_code == 200

    # 7. Verify results
    # Food should have been reset to automated (forecast)
    food_budget = MonthlyBudget.objects.get(user=user, category=cat1, month=current_month_date)
    assert food_budget.user_amount is None
    assert food_budget.is_automated is True

    # Check HTMX response content for the message
    content = response.content.decode()
    assert 'Nessun budget trovato per il mese scorso' in content
    assert 'hx-swap-oob="true"' in content
    assert 'messages-container' in content
