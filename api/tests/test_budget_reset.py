import pytest
import datetime
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Category, MonthlyBudget

@pytest.mark.django_db
def test_budget_reset_view(client):
    """Test that the budget reset view correctly resets manual inputs to automated values"""
    # Setup
    user = User.objects.create_user(username='resetuser', password='password')
    client.login(username='resetuser', password='password')

    cat = Category.objects.create(name='Food', user=user)
    # Use a specific date to avoid issues with "next month" logic if it were dynamic
    year, month = 2026, 4
    month_date = datetime.date(year, month, 1)

    # Create a budget with manual input
    budget = MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=month_date,
        planned_amount=100.0,
        user_amount=150.0,
        is_automated=False
    )

    url = reverse('budget_reset', kwargs={'year': year, 'month': month})
    
    # 1. Test standard POST (redirect)
    response = client.post(url)
    assert response.status_code == 302
    assert response.url == reverse('budget_forecast_detail', kwargs={'year': year, 'month': month})
    
    budget.refresh_from_db()
    assert budget.is_automated is True
    assert budget.user_amount is None
    assert float(budget.final_amount) == 100.0

    # 2. Reset it back to manual for HTMX test
    budget.user_amount = 200.0
    budget.is_automated = False
    budget.save()

    # Test HTMX POST
    response = client.post(url, HTTP_HX_REQUEST='true')
    assert response.status_code == 200
    
    budget.refresh_from_db()
    assert budget.is_automated is True
    assert budget.user_amount is None
    
    content = response.content.decode()
    # Check for OOB swaps (main card and summary)
    assert 'hx-swap-oob="true"' in content
    # Check for budget list content
    assert 'Food' in content
    assert 'Previsione' in content
    assert '100.00' in content
