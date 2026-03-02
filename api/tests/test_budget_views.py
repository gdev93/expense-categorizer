import pytest
from django.urls import reverse
from django.utils import timezone
import datetime
from api.models import MonthlyBudget, Category
from django.contrib.auth.models import User

@pytest.mark.django_db
def test_monthly_budget_forecast_view(client):
    # 1. Setup user
    user = User.objects.create_user(username='testuser', password='password')
    client.login(username='testuser', password='password')

    # 2. Setup categories
    cat1 = Category.objects.create(name='Food', user=user)
    cat2 = Category.objects.create(name='Rent', user=user)

    # 3. Setup next month date (same logic as in the view/task)
    today = timezone.now().date()
    next_month_date = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)

    # 4. Create forecasts
    MonthlyBudget.objects.create(
        user=user,
        category=cat1,
        month=next_month_date,
        planned_amount=150.00,
        is_automated=True
    )
    MonthlyBudget.objects.create(
        user=user,
        category=cat2,
        month=next_month_date,
        planned_amount=1200.00,
        is_automated=False
    )

    # 5. Access the view
    url = reverse('budget_forecast')
    response = client.get(url)

    # 6. Verify response
    assert response.status_code == 200
    assert 'forecasts' in response.context
    assert len(response.context['forecasts']) == 2
    
    # Verify context data from dataclass
    assert response.context['next_month'] == next_month_date
    assert float(response.context['total_planned']) == 1350.00
    
    # Verify template content
    content = response.content.decode()
    assert 'Previsioni Budget' in content
    assert 'Food' in content
    assert 'Rent' in content
    assert '150.00' in content
    assert '1200.00' in content
    assert '1350,00' in content
    assert 'Previsione AI' in content
    assert 'Budget Manuale' in content

@pytest.mark.django_db
def test_monthly_budget_update_view(client):
    user = User.objects.create_user(username='updateuser', password='password')
    client.login(username='updateuser', password='password')
    
    cat = Category.objects.create(name='Coffee', user=user)
    today = timezone.now().date()
    next_month_date = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    
    budget = MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=next_month_date,
        planned_amount=50.00,
        is_automated=True
    )
    
    # 1. Test standard POST
    url = reverse('budget_update', kwargs={'pk': budget.pk})
    response = client.post(url, {'amount': '75.50'})
    
    assert response.status_code == 302
    budget.refresh_from_db()
    assert float(budget.user_amount) == 75.50
    assert budget.is_automated is False
    
    # 2. Test HTMX POST
    response = client.post(url, {'amount': '100,00'}, HTTP_HX_REQUEST='true')
    assert response.status_code == 200
    budget.refresh_from_db()
    assert float(budget.user_amount) == 100.00
    
    # Verify OOB swap in response and that list content is present
    content = response.content.decode()
    assert 'hx-swap-oob="true"' in content
    assert '100,00' in content
    assert 'Coffee' in content
    assert 'Budget Manuale' in content

@pytest.mark.django_db
def test_navigation_item_present(client):
    user = User.objects.create_user(username='navuser', password='password')
    client.login(username='navuser', password='password')

    # The index page should have the link
    response = client.get(reverse('transaction_list'))
    assert response.status_code == 200
    content = response.content.decode()
    
    # Check for the link and text
    assert reverse('budget_forecast_list') in content
    assert 'Previsioni budget' in content
    assert 'analytics' in content

@pytest.mark.django_db
def test_monthly_budget_forecast_view_no_data(client):
    user = User.objects.create_user(username='testuser2', password='password')
    client.login(username='testuser2', password='password')

    url = reverse('budget_forecast')
    response = client.get(url)

    assert response.status_code == 200
    assert len(response.context['forecasts']) == 0
    assert 'Nessuna previsione trovata per il mese prossimo.' in response.content.decode()

@pytest.mark.django_db
def test_monthly_budget_forecast_view_login_required(client):
    url = reverse('budget_forecast')
    response = client.get(url)
    
    # Should redirect to login
    assert response.status_code == 302
    assert 'accounts/login' in response.url

@pytest.mark.django_db
def test_monthly_budget_forecast_view_post(client):
    user = User.objects.create_user(username='testuser', password='password')
    client.login(username='testuser', password='password')
    
    today = timezone.now().date()
    next_month_date = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    
    from unittest.mock import patch
    with patch('api.services.ForecastService.compute_forecast') as mock_compute:
        response = client.post(reverse('budget_forecast'), {
            'month': str(next_month_date.month),
            'year': str(next_month_date.year)
        })
        
        # Current implementation will probably return 200 with string content (the URL string)
        # We want it to be 302 after fix.
        assert response.status_code == 302
        assert response.url == reverse('budget_forecast')
        mock_compute.assert_any_call(user=user, months=[next_month_date.month], years=[next_month_date.year])

@pytest.mark.django_db
def test_monthly_budget_forecast_view_htmx_post(client):
    user = User.objects.create_user(username='testuser_htmx', password='password')
    client.login(username='testuser_htmx', password='password')
    
    cat = Category.objects.create(name='Coffee', user=user)
    today = timezone.now().date()
    next_month_date = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    
    # Pre-create a budget
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=next_month_date,
        planned_amount=50.00,
        is_automated=True
    )
    
    from unittest.mock import patch
    with patch('api.services.ForecastService.compute_forecast') as mock_compute:
        # Mock compute_forecast to simulate budget update
        def update_budget(*args, **kwargs):
            MonthlyBudget.objects.filter(user=user, category=cat, month=next_month_date).update(planned_amount=75.00)
            
        mock_compute.side_effect = update_budget
        
        response = client.post(reverse('budget_forecast'), {
            'month': str(next_month_date.month),
            'year': str(next_month_date.year)
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()

        # Verify list partial content
        assert 'Coffee' in content
        assert '75.00' in content

        # Verify OOB summary content
        assert 'hx-swap-oob="true"' in content
        assert 'Totale Pianificato' in content
        assert '75,00' in content

        # Check that it was called at least once with the expected arguments
        mock_compute.assert_any_call(user=user, months=[next_month_date.month], years=[next_month_date.year])

@pytest.mark.django_db
def test_budget_spent_percentage_display(client):
    # 1. Setup user
    user = User.objects.create_user(username='testspent', password='password')
    client.login(username='testspent', password='password')
    
    # 2. Setup category
    cat = Category.objects.create(name='Food', user=user)
    
    # 3. Setup dates - use current month to ensure we can see the spent info
    today = timezone.now().date()
    current_month_date = today.replace(day=1)
    
    # 4. Create a budget
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=current_month_date,
        planned_amount=100.00,
        is_automated=True
    )
    
    # 5. Create some transactions for this category and month
    from api.models import Transaction
    Transaction.objects.create(
        user=user,
        category=cat,
        amount=55.50,
        transaction_date=current_month_date,
        transaction_type='expense',
        status='categorized'
    )
    from api.services import RollupService
    RollupService.update_all_rollups(user, [(current_month_date.year, current_month_date.month)])
    
    # 6. Access the detail view
    from django.urls import reverse
    url = reverse('budget_forecast_detail', kwargs={'year': current_month_date.year, 'month': current_month_date.month})
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    # 7. Verify spent info is in the response
    assert 'Speso:' in content
    assert '55.50' in content
    assert '55,5%' in content or '55.5%' in content
    assert 'spent-info' in content

@pytest.mark.django_db
def test_budget_spent_percentage_over_budget(client):
    user = User.objects.create_user(username='testover', password='password')
    client.login(username='testover', password='password')
    cat = Category.objects.create(name='Rent', user=user)
    today = timezone.now().date()
    current_month_date = today.replace(day=1)
    
    MonthlyBudget.objects.create(
        user=user,
        category=cat,
        month=current_month_date,
        planned_amount=1000.00,
        is_automated=True
    )
    
    from api.models import Transaction
    Transaction.objects.create(
        user=user,
        category=cat,
        amount=1100.00,
        transaction_date=current_month_date,
        transaction_type='expense',
        status='categorized'
    )
    from api.services import RollupService
    RollupService.update_all_rollups(user, [(current_month_date.year, current_month_date.month)])
    
    url = reverse('budget_forecast_detail', kwargs={'year': current_month_date.year, 'month': current_month_date.month})
    response = client.get(url)
    
    assert response.status_code == 200
    content = response.content.decode()
    
    assert 'Speso:' in content
    assert '1100.00' in content
    assert '110,0%' in content or '110.0%' in content
    assert 'over-budget' in content
