import pytest
import numpy as np
from django.core.management import call_command
from django.contrib.auth.models import User
from api.models import Merchant, MerchantEMA, Transaction, FileStructureMetadata, UploadFile

@pytest.mark.django_db
def test_rebuild_ema_command() -> None:
    """
    Tests that the rebuild_ema management command correctly clears and regenerates MerchantEMA records.
    """
    # Setup data
    user = User.objects.create_user(username='testuser_rebuild', password='password')
    merchant = Merchant.objects.create(name='Test Merchant', user=user)
    fs_metadata = FileStructureMetadata.objects.create(row_hash='test_rebuild_hash')
    upload_file = UploadFile.objects.create(
        user=user, 
        file_structure_metadata=fs_metadata,
        status='completed'
    )
    
    # Create transactions in chronological order
    # Note: MerchantEMA rebuild uses both transaction_date and created_at for sorting
    Transaction.objects.create(
        user=user,
        merchant=merchant,
        upload_file=upload_file,
        description='Coffee Shop payment',
        transaction_date='2026-01-01',
        amount=5.50
    )
    Transaction.objects.create(
        user=user,
        merchant=merchant,
        upload_file=upload_file,
        description='Coffee Shop morning',
        transaction_date='2026-01-02',
        amount=4.50
    )
    
    # Create an initial EMA that should be cleared
    dummy_vector = [0.99] * 384
    MerchantEMA.objects.create(
        merchant=merchant,
        file_structure_metadata=fs_metadata,
        digital_footprint=dummy_vector
    )
    
    assert MerchantEMA.objects.filter(merchant=merchant).count() == 1
    
    # Execute the command
    call_command('rebuild_ema')
    
    # Verify results
    # There should be exactly one EMA record for this merchant/fs_metadata pair
    emas = MerchantEMA.objects.filter(merchant=merchant, file_structure_metadata=fs_metadata)
    assert emas.count() == 1
    
    ema = emas.first()
    # The digital footprint should be regenerated and thus different from the dummy vector
    # Using np.allclose to compare floating point vectors
    assert not np.allclose(ema.digital_footprint, dummy_vector, atol=1e-5)
    assert len(ema.digital_footprint) == 384
    
    # Verify that it didn't create EMAs for other merchants (none exist)
    assert MerchantEMA.objects.count() == 1

@pytest.mark.django_db
def test_rebuild_ema_multiple_merchants() -> None:
    """
    Tests the command with multiple merchants and file structures.
    """
    user = User.objects.create_user(username='testuser_multi', password='password')
    fs1 = FileStructureMetadata.objects.create(row_hash='hash1')
    fs2 = FileStructureMetadata.objects.create(row_hash='hash2')
    
    m1 = Merchant.objects.create(name='Merchant 1', user=user)
    m2 = Merchant.objects.create(name='Merchant 2', user=user)
    
    up1 = UploadFile.objects.create(user=user, file_structure_metadata=fs1)
    up2 = UploadFile.objects.create(user=user, file_structure_metadata=fs2)
    
    # M1 in FS1
    Transaction.objects.create(user=user, merchant=m1, upload_file=up1, description='M1 FS1')
    # M1 in FS2
    Transaction.objects.create(user=user, merchant=m1, upload_file=up2, description='M1 FS2')
    # M2 in FS1
    Transaction.objects.create(user=user, merchant=m2, upload_file=up1, description='M2 FS1')
    
    # Execute command
    call_command('rebuild_ema')
    
    # Should have 3 EMA records
    assert MerchantEMA.objects.count() == 3
    assert MerchantEMA.objects.filter(merchant=m1).count() == 2
    assert MerchantEMA.objects.filter(merchant=m2).count() == 1
    assert MerchantEMA.objects.filter(file_structure_metadata=fs1).count() == 2
    assert MerchantEMA.objects.filter(file_structure_metadata=fs2).count() == 1
