import pytest
from django.contrib.auth.models import User
from api.models import Transaction, Category, Profile, UploadFile
from api.services.rollups.rollup_service import RollupService
from api.tasks import populate_rollups
from decimal import Decimal
import datetime

@pytest.mark.django_db
def test_rollup_dirty_flag_on_transaction_changes():
    user = User.objects.create_user(username='testuser', password='password')
    # Profile is created by signal or during signup. If not, create it.
    profile, _ = Profile.objects.get_or_create(user=user)
    
    # Initially dirty (default is True)
    assert profile.needs_rollup_recomputation is True
    
    # Manually set to False to test signals
    profile.needs_rollup_recomputation = False
    profile.save()
    
    # 1. Create transaction
    cat = Category.objects.create(name='Food', user=user)
    tx = Transaction.objects.create(
        user=user,
        amount=Decimal('10.00'),
        transaction_date=datetime.date(2025, 1, 1),
        category=cat,
        transaction_type='expense'
    )
    
    profile.refresh_from_db()
    assert profile.needs_rollup_recomputation is True
    
    # Reset and test update
    profile.needs_rollup_recomputation = False
    profile.save()
    
    tx.amount = Decimal('20.00')
    tx.save()
    
    profile.refresh_from_db()
    assert profile.needs_rollup_recomputation is True
    
    # Reset and test delete
    profile.needs_rollup_recomputation = False
    profile.save()
    
    tx.delete()
    
    profile.refresh_from_db()
    assert profile.needs_rollup_recomputation is True

@pytest.mark.django_db
def test_rollup_dirty_flag_on_upload_delete():
    user = User.objects.create_user(username='uploaduser', password='password')
    profile, _ = Profile.objects.get_or_create(user=user)
    
    upload = UploadFile.objects.create(user=user, file_name='test.csv')
    
    profile.needs_rollup_recomputation = False
    profile.save()
    
    upload.delete()
    
    profile.refresh_from_db()
    assert profile.needs_rollup_recomputation is True

@pytest.mark.django_db
def test_update_all_rollups_clears_flag():
    user = User.objects.create_user(username='cleanuser', password='password')
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.needs_rollup_recomputation = True
    profile.save()
    
    RollupService.update_all_rollups(user, [])
    
    profile.refresh_from_db()
    assert profile.needs_rollup_recomputation is False

@pytest.mark.django_db
def test_task_skips_clean_users():
    user1 = User.objects.create_user(username='dirtyuser', password='password')
    Profile.objects.get_or_create(user=user1)
    Profile.objects.filter(user=user1).update(needs_rollup_recomputation=True)
    
    user2 = User.objects.create_user(username='cleanuser', password='password')
    Profile.objects.get_or_create(user=user2)
    Profile.objects.filter(user=user2).update(needs_rollup_recomputation=False)
    
    # Add transaction to dirty user so there's something to process
    Transaction.objects.create(
        user=user1,
        amount=Decimal('10.00'),
        transaction_date=datetime.date(2025, 1, 1),
        transaction_type='expense'
    )
    
    from unittest.mock import patch
    with patch('api.services.rollups.rollup_service.RollupService.update_all_rollups') as mock_update:
        populate_rollups()
        
        # Should only be called for user1
        assert mock_update.call_count == 1
        # Check that the first argument of the first call is user1
        assert mock_update.call_args_list[0][0][0] == user1
