import os
import pytest
from unittest.mock import patch
from django.core.management import call_command
from django.conf import settings
from api.models import Merchant, Transaction
from api.privacy_utils import generate_blind_index, encrypt_value

@pytest.mark.django_db
class TestRotateKeysCommand:
    def setup_method(self):
        # Initial setup with a known key
        self.old_key = "old-secret-key-for-testing-purposes"
        self.new_key = "new-secret-key-for-testing-purposes"
        
        # Ensure we start with the old key in settings
        self.original_secret_key = settings.SECRET_KEY
        settings.SECRET_KEY = self.old_key
        
        # Create a user
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username="testuser")
        
        # Create test data
        self.merchant = Merchant.objects.create(name="Test Merchant", user=self.user)
        self.transaction = Transaction.objects.create(
            description="Test Transaction",
            amount="123.45",
            user=self.user
        )
        
        # Capture old values for verification using raw SQL to get encrypted data
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM api_merchant WHERE id = %s", [self.merchant.id])
            self.old_merchant_encrypted = cursor.fetchone()[0]
            
            cursor.execute("SELECT description, amount FROM api_transaction WHERE id = %s", [self.transaction.id])
            row = cursor.fetchone()
            self.old_tx_desc_encrypted = row[0]
            self.old_tx_amount_encrypted = row[1]

        self.old_merchant_hash = self.merchant.name_hash
        self.old_tx_desc_hash = self.transaction.description_hash

    def teardown_method(self):
        settings.SECRET_KEY = self.original_secret_key

    def test_rotate_keys_success(self, monkeypatch):
        # Set environment variables
        monkeypatch.setenv("OLD_CRYPTO_KEY", self.old_key)
        monkeypatch.setenv("NEW_CRYPTO_KEY", self.new_key)
        
        # Run rotation command
        call_command('rotate_keys', '--rotate')
        
        # Refresh from DB
        self.merchant.refresh_from_db()
        self.transaction.refresh_from_db()
        
        # 1. Verify that blind indexes have changed
        assert self.merchant.name_hash != self.old_merchant_hash
        assert self.transaction.description_hash != self.old_tx_desc_hash
        
        # 2. Verify that encrypted values have changed in the DB
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM api_merchant WHERE id = %s", [self.merchant.id])
            new_merchant_encrypted = cursor.fetchone()[0]
            
            cursor.execute("SELECT description, amount FROM api_transaction WHERE id = %s", [self.transaction.id])
            row = cursor.fetchone()
            new_tx_desc_encrypted = row[0]
            new_tx_amount_encrypted = row[1]
            
        assert new_merchant_encrypted != self.old_merchant_encrypted
        assert new_tx_desc_encrypted != self.old_tx_desc_encrypted
        assert new_tx_amount_encrypted != self.old_tx_amount_encrypted
        
        # 3. Verify that with the OLD key, we cannot decrypt anymore
        # (EncryptedCharField returns empty string/Decimal('0.00') on failure)
        assert self.merchant.name == ""
        assert self.transaction.description == ""
        from decimal import Decimal
        assert self.transaction.amount == Decimal('0.00')
        
        # 4. Temporarily switch to the NEW key and verify decryption
        settings.SECRET_KEY = self.new_key
        
        # Refresh from DB to trigger re-decryption with new key
        self.merchant.refresh_from_db()
        self.transaction.refresh_from_db()
            
        assert self.merchant.name == "Test Merchant"
        assert self.transaction.description == "Test Transaction"
        assert str(self.transaction.amount) == "123.45"
        
        # 5. Verify blind indexes match the ones generated with the new key
        assert self.merchant.name_hash == generate_blind_index("Test Merchant")
        assert self.transaction.description_hash == generate_blind_index("Test Transaction")

    def test_rotate_keys_no_flag(self, capsys):
        # Run rotation command without flag
        call_command('rotate_keys')
        
        captured = capsys.readouterr()
        assert 'Safety flag --rotate is missing' in captured.out
        
        # Verify nothing changed
        self.merchant.refresh_from_db()
        assert self.merchant.name_hash == self.old_merchant_hash

    def test_rotate_keys_missing_env(self, monkeypatch):
        # Remove env vars if they exist
        monkeypatch.delenv("OLD_CRYPTO_KEY", raising=False)
        monkeypatch.delenv("NEW_CRYPTO_KEY", raising=False)
        
        with pytest.raises(Exception) as excinfo:
            call_command('rotate_keys', '--rotate')
        
        assert 'Both OLD_CRYPTO_KEY and NEW_CRYPTO_KEY environment variables must be set' in str(excinfo.value)

    def test_rotate_keys_fails_alltogether_on_exception(self, monkeypatch):
        # Set environment variables
        monkeypatch.setenv("OLD_CRYPTO_KEY", self.old_key)
        monkeypatch.setenv("NEW_CRYPTO_KEY", self.new_key)
        
        # Mocking save to raise an exception for transactions but NOT for merchants
        original_save = Transaction.save
        
        def mock_save(self_instance, *args, **kwargs):
            if self_instance.description == "Test Transaction":
                raise Exception("Simulated failure during Transaction rotation")
            return original_save(self_instance, *args, **kwargs)

        with patch.object(Transaction, 'save', autospec=True, side_effect=mock_save):
            # Run rotation command, it should raise an exception
            with pytest.raises(Exception) as excinfo:
                call_command('rotate_keys', '--rotate')
            
            assert "Simulated failure during Transaction rotation" in str(excinfo.value)

        # Refresh from DB
        self.merchant.refresh_from_db()
        self.transaction.refresh_from_db()
        
        # If atomic transaction worked and we didn't swallow the error,
        # merchant hash SHOULD still be the old one (rollback)
        assert self.merchant.name_hash == self.old_merchant_hash, "Merchant hash should have been rolled back"
        assert self.transaction.description_hash == self.old_tx_desc_hash, "Transaction hash should have been rolled back"
