import pytest
from decimal import Decimal
from django.utils import timezone
import datetime
from api.models import Transaction, Category, CategoryRollup
from api.services.rollups.rollup_service import RollupService
from django.contrib.auth.models import User

@pytest.mark.django_db
def test_category_rollup_population():
    # Setup user
    user = User.objects.create_user(username='testrollup', password='password')
    
    # Setup categories
    cat1 = Category.objects.create(name='Food', user=user)
    cat2 = Category.objects.create(name='Utilities', user=user)
    
    # Create transactions
    # March 2026 (current month for our context)
    Transaction.objects.create(
        user=user, category=cat1, amount=Decimal('50.00'),
        transaction_date=datetime.date(2026, 3, 1), transaction_type='expense', status='categorized'
    )
    Transaction.objects.create(
        user=user, category=cat1, amount=Decimal('25.50'),
        transaction_date=datetime.date(2026, 3, 10), transaction_type='expense', status='categorized'
    )
    Transaction.objects.create(
        user=user, category=cat2, amount=Decimal('100.00'),
        transaction_date=datetime.date(2026, 3, 15), transaction_type='expense', status='categorized'
    )
    
    # February 2026
    Transaction.objects.create(
        user=user, category=cat1, amount=Decimal('40.00'),
        transaction_date=datetime.date(2026, 2, 1), transaction_type='expense', status='categorized'
    )
    
    # Run rollup
    years_months = [(2026, 3), (2026, 2)]
    RollupService.update_category_rollup(user, years_months)
    
    # Verify March Category 1 (Food)
    rollup_march_cat1 = CategoryRollup.objects.get(user=user, category=cat1, year=2026, month_number=3)
    assert float(rollup_march_cat1.total_spent) == 75.50
    
    # Verify March Category 2 (Utilities)
    rollup_march_cat2 = CategoryRollup.objects.get(user=user, category=cat2, year=2026, month_number=3)
    assert float(rollup_march_cat2.total_spent) == 100.00
    
    # Verify February Category 1 (Food)
    rollup_feb_cat1 = CategoryRollup.objects.get(user=user, category=cat1, year=2026, month_number=2)
    assert float(rollup_feb_cat1.total_spent) == 40.00
    
    # Verify Yearly totals
    yearly_cat1 = CategoryRollup.objects.get(user=user, category=cat1, year=2026, month_number=None)
    assert float(yearly_cat1.total_spent) == 115.50
    
    yearly_cat2 = CategoryRollup.objects.get(user=user, category=cat2, year=2026, month_number=None)
    assert float(yearly_cat2.total_spent) == 100.00

@pytest.mark.django_db
def test_category_rollup_updates_on_deletion():
    user = User.objects.create_user(username='testrollup_del', password='password')
    cat = Category.objects.create(name='Food', user=user)
    
    tx = Transaction.objects.create(
        user=user, category=cat, amount=Decimal('50.00'),
        transaction_date=datetime.date(2026, 3, 1), transaction_type='expense', status='categorized'
    )
    
    RollupService.update_category_rollup(user, [(2026, 3)])
    
    rollup = CategoryRollup.objects.get(user=user, category=cat, year=2026, month_number=3)
    assert float(rollup.total_spent) == 50.00
    
    # Delete transaction and update rollup
    tx.delete()
    RollupService.update_category_rollup(user, [(2026, 3)])
    
    rollup.refresh_from_db()
    assert float(rollup.total_spent) == 0.00
