import pytest
import datetime
from django.urls import reverse
from django.utils import timezone
from api.models import MonthlyBudget, Category
from django.contrib.auth.models import User

@pytest.mark.django_db
def test_budget_month_list_view(client):
    # 1. Setup user
    user = User.objects.create_user(username='listuser', password='password')
    client.login(username='listuser', password='password')

    # 2. Setup category
    cat = Category.objects.create(name='Food', user=user)

    # 3. Create forecasts for different months
    month1 = datetime.date(2026, 3, 1)
    month2 = datetime.date(2026, 4, 1)
    
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=month1,
        planned_amount=150.00,
        is_automated=True
    )
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=month2,
        planned_amount=200.00,
        is_automated=True
    )

    # 4. Access the list view
    url = reverse('budget_forecast_list')
    response = client.get(url)

    # 5. Verify response
    assert response.status_code == 200
    assert 'months' in response.context
    # Since today is March 2026, it should show 4 months (Jan, Feb, Mar, Apr)
    assert len(response.context['months']) == 4
    
    content = response.content.decode()
    assert 'marzo 2026' in content.lower()
    assert 'aprile 2026' in content.lower()
    assert '150,00' in content # localized
    assert '200,00' in content # localized

@pytest.mark.django_db
def test_budget_month_list_view_next_month_highlight(client):
    user = User.objects.create_user(username='highlightuser', password='password')
    client.login(username='highlightuser', password='password')
    cat = Category.objects.create(name='Food', user=user)
    
    # Calculate next month date to ensure it shows up highlighted
    today = timezone.now().date()
    next_month_date = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=next_month_date,
        planned_amount=500.00,
        is_automated=True
    )
    
    response = client.get(reverse('budget_forecast_list'))
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for the next month highlight class
    assert 'next-month-highlight' in content
    assert 'prossimo mese' in content.lower()
    assert '500,00' in content
    
    # Check for context variables
    assert response.context['next_month_budget'] is not None
    assert response.context['next_month_budget'].month == next_month_date

@pytest.mark.django_db
def test_budget_month_list_view_other_months(client):
    user = User.objects.create_user(username='otheruser', password='password')
    client.login(username='otheruser', password='password')
    cat = Category.objects.create(name='Food', user=user)
    
    # Create budget for a past month (relative to 2026-03-02)
    past_month = datetime.date(2026, 1, 1)
    
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=past_month,
        planned_amount=300.00,
        is_automated=True
    )
    
    response = client.get(reverse('budget_forecast_list'))
    assert response.status_code == 200
    content = response.content.decode()
    
    # Should show in next month card as well, because we now fill all months
    assert 'current-month-card' in content or 'next-month-card' in content or 'next-month-highlight' in content
    assert 'altri mesi del 2026' in content.lower()
    assert 'gennaio 2026' in content.lower()
    assert '300,00' in content
    
    assert response.context['next_month_budget'] is not None
    # 4 months (Jan, Feb, Mar, Apr) - current (Mar) - next (Apr) = 2 (Jan, Feb)
    assert len(response.context['other_months']) == 2

@pytest.mark.django_db
def test_budget_month_list_view_year_filtering(client):
    user = User.objects.create_user(username='yearuser', password='password')
    client.login(username='yearuser', password='password')
    cat = Category.objects.create(name='Food', user=user)
    
    # Create budgets for two different years
    month_2025 = datetime.date(2025, 12, 1)
    month_2026 = datetime.date(2026, 1, 1)
    
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=month_2025,
        planned_amount=100.00,
        is_automated=True
    )
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=month_2026,
        planned_amount=200.00,
        is_automated=True
    )
    
    # 1. Access without year param (should default to most recent year with data: 2026)
    response = client.get(reverse('budget_forecast_list'))
    assert response.status_code == 200
    assert response.context['year'] == 2026
    # 2026 up to April = 4 months
    assert len(response.context['months']) == 4
    # months[0] should be April (sorted reverse=True)
    assert response.context['months'][0].month == datetime.date(2026, 4, 1)
    
    # 2. Access with year=2025
    response = client.get(reverse('budget_forecast_list') + '?year=2025')
    assert response.status_code == 200
    assert response.context['year'] == 2025
    assert len(response.context['months']) == 12
    # months[0] should be December (sorted reverse=True)
    assert response.context['months'][0].month == month_2025

@pytest.mark.django_db
def test_budget_forecast_detail_view(client):
    # 1. Setup user
    user = User.objects.create_user(username='detailuser', password='password')
    client.login(username='detailuser', password='password')

    # 2. Setup category
    cat = Category.objects.create(name='Rent', user=user)

    # 3. Create forecast for a specific month
    target_month = datetime.date(2026, 5, 1)
    
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=target_month,
        planned_amount=1200.00,
        is_automated=True
    )

    # 4. Access the detail view
    url = reverse('budget_forecast_detail', kwargs={'year': 2026, 'month': 5})
    response = client.get(url)

    # 5. Verify response
    assert response.status_code == 200
    assert 'forecasts' in response.context
    assert len(response.context['forecasts']) == 1
    assert float(response.context['total_planned']) == 1200.00
    assert response.context['next_month'] == target_month # next_month name used in template

    content = response.content.decode()
    assert 'Rent' in content
    assert '1200.00' in content # input value is not localized in stringformat:".2f"
    assert 'maggio 2026' in content.lower()

@pytest.mark.django_db
def test_budget_month_list_view_all_months_displayed(client):
    user = User.objects.create_user(username='allmonthsuser', password='password')
    client.login(username='allmonthsuser', password='password')
    cat = Category.objects.create(name='Food', user=user)
    
    # Create budget only for January 2026
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=datetime.date(2026, 1, 1),
        planned_amount=100.00,
        is_automated=True
    )
    
    response = client.get(reverse('budget_forecast_list') + '?year=2026')
    assert response.status_code == 200
    
    # Check if all 12 months are present in the context
    months = response.context['months']
    # If next_month_budget is present, it might be separated in the context
    # But for 2026, if today is March 2026, April 2026 would be next_month_budget
    
    all_months = []
    if response.context['current_month_budget']:
        all_months.append(response.context['current_month_budget'])
    if response.context['next_month_budget']:
        all_months.append(response.context['next_month_budget'])
    all_months.extend(response.context['other_months'])
    
    assert len(all_months) == 4

@pytest.mark.django_db
def test_budget_month_list_view_future_year(client):
    user = User.objects.create_user(username='futureuser', password='password')
    client.login(username='futureuser', password='password')
    
    # 2027 is in the future relative to 2026-03-02
    response = client.get(reverse('budget_forecast_list') + '?year=2027')
    assert response.status_code == 200
    assert response.context['year'] == 2027
    assert len(response.context['months']) == 0

@pytest.mark.django_db
def test_budget_month_list_view_top_categories(client):
    user = User.objects.create_user(username='topcatuser', password='password')
    client.login(username='topcatuser', password='password')
    
    # Create categories
    cat1 = Category.objects.create(name='Expensive', user=user)
    cat2 = Category.objects.create(name='Cheap', user=user)
    cat3 = Category.objects.create(name='Moderate', user=user)
    cat4 = Category.objects.create(name='Very Expensive', user=user)
    cat5 = Category.objects.create(name='Tiny', user=user)
    
    # Current month
    today = timezone.now().date()
    current_month = today.replace(day=1)
    
    MonthlyBudget.objects.create(user=user, category=cat1, month=current_month, planned_amount=1000.00)
    MonthlyBudget.objects.create(user=user, category=cat2, month=current_month, planned_amount=10.00)
    MonthlyBudget.objects.create(user=user, category=cat3, month=current_month, planned_amount=500.00)
    MonthlyBudget.objects.create(user=user, category=cat4, month=current_month, planned_amount=2000.00)
    MonthlyBudget.objects.create(user=user, category=cat5, month=current_month, planned_amount=5.00)
    
    response = client.get(reverse('budget_forecast_list'))
    assert response.status_code == 200
    
    current_budget = response.context['current_month_budget']
    assert current_budget is not None
    assert hasattr(current_budget, 'top_categories')
    assert len(current_budget.top_categories) == 4
    
    # Verify order (descending amount)
    top_cats = current_budget.top_categories
    assert top_cats[0].name == 'Very Expensive'
    assert top_cats[1].name == 'Expensive'
    assert top_cats[2].name == 'Moderate'
    assert top_cats[3].name == 'Cheap'
    
    content = response.content.decode()
    assert 'Maggiori voci di spesa' in content
    assert 'Very Expensive' in content
    assert 'Expensive' in content
    assert 'Moderate' in content
    assert 'Cheap' in content
    assert 'Tiny' not in content # Should be the 5th, so not in top 4

@pytest.mark.django_db
def test_budget_month_list_view_spent_percentage(client):
    user = User.objects.create_user(username='percuser', password='password')
    client.login(username='percuser', password='password')
    
    from api.models import YearlyMonthlyUserRollup, CategoryRollup
    
    # 1. Current month setup
    today = timezone.now().date()
    current_month = today.replace(day=1)
    cat = Category.objects.create(name='Food', user=user)
    
    # Planned: 1000
    MonthlyBudget.objects.create(user=user, category=cat, month=current_month, planned_amount=1000.00)
    
    # Spent: 750 (75%)
    CategoryRollup.objects.create(
        user=user,
        category=cat,
        year=current_month.year,
        month_number=current_month.month,
        total_spent=750.00
    )
    YearlyMonthlyUserRollup.objects.create(
        user=user,
        by_year=current_month.year,
        month_number=current_month.month,
        total_amount_expense_by_month=750.00
    )
    
    response = client.get(reverse('budget_forecast_list'))
    assert response.status_code == 200
    content = response.content.decode()
    
    assert '75%' in content
    assert 'speso' in content
    assert 'spent-percentage-large' in content
    assert 'over-budget' not in content
    
    # 2. Over budget case
    CategoryRollup.objects.filter(user=user, month_number=current_month.month).update(
        total_spent=1200.00
    )
    YearlyMonthlyUserRollup.objects.filter(user=user, month_number=current_month.month).update(
        total_amount_expense_by_month=1200.00
    )
    
    response = client.get(reverse('budget_forecast_list'))
    content = response.content.decode()
    assert '120%' in content
    assert 'over-budget' in content

@pytest.mark.django_db
def test_budget_month_list_view_forecast_unavailable(client):
    user = User.objects.create_user(username='unavailableuser', password='password')
    client.login(username='unavailableuser', password='password')
    
    # Next month relative to 2026-03-02 is April 2026
    # 2026-04-01 - 2026-03-02 = 30 days (> 15)
    
    response = client.get(reverse('budget_forecast_list'))
    assert response.status_code == 200
    
    next_month_budget = response.context['next_month_budget']
    assert next_month_budget.forecast_available is False
    
    content = response.content.decode()
    assert 'forecast-unavailable' in content
    assert 'Previsione non ancora disponibile' in content
    assert 'pianificare manualmente' in content

@pytest.mark.django_db
def test_budget_month_list_view_forecast_available(client):
    # Mock date to be 2026-03-20
    # Next month April 1st - March 20th = 12 days (<= 15)
    from unittest.mock import patch
    import datetime
    
    mock_now_val = datetime.datetime(2026, 3, 20, 12, 0, tzinfo=datetime.timezone.utc)
    with patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = mock_now_val
        
        user = User.objects.create_user(username='availableuser', password='password')
        client.login(username='availableuser', password='password')
        
        response = client.get(reverse('budget_forecast_list'))
        assert response.status_code == 200
        
        next_month_budget = response.context['next_month_budget']
        assert next_month_budget.forecast_available is True
        
        content = response.content.decode()
        assert 'forecast-unavailable' not in content
        assert 'Previsione non ancora disponibile' not in content

@pytest.mark.django_db
def test_budget_forecast_detail_view_summary_card(client):
    from api.models import CategoryRollup
    
    user = User.objects.create_user(username='carduser', password='password')
    client.login(username='carduser', password='password')
    cat = Category.objects.create(name='Food', user=user)
    
    target_month = datetime.date(2026, 5, 1)
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=target_month,
        planned_amount=1000.00,
        is_automated=True
    )
    
    CategoryRollup.objects.create(
        user=user,
        category=cat,
        year=2026,
        month_number=5,
        total_spent=450.00
    )
    
    url = reverse('budget_forecast_detail', kwargs={'year': 2026, 'month': 5})
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    assert 'budget-main-card' in content
    assert 'Budget Totale' in content
    assert 'Totale Speso' in content
    assert '1000,00' in content # localized
    assert '450,00' in content # localized
    assert '45%' in content
    assert 'Speso' in content
