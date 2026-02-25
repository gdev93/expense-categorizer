import os
import hashlib
import hmac
import base64
from typing import Any
from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings
from api.models import Merchant, Transaction

class Command(BaseCommand):
    help = 'Rotates cryptographic keys for Merchant and Transaction models.'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--rotate',
            action='store_true',
            help='Explicitly allow key rotation.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # 1. Safety check
        if not options.get('rotate'):
            self.stdout.write(self.style.WARNING(
                'Safety flag --rotate is missing. Command will not execute.'
            ))
            return

        # 2. Environment variables validation
        old_key = os.environ.get('OLD_CRYPTO_KEY')
        new_key = os.environ.get('NEW_CRYPTO_KEY')

        if not old_key or not new_key:
            raise CommandError('Both OLD_CRYPTO_KEY and NEW_CRYPTO_KEY environment variables must be set.')

        self.stdout.write('Starting cryptographic key rotation process...')

        # Initialize old Fernet for manual decryption
        old_fernet_key = hashlib.sha256(old_key.encode()).digest()
        old_fernet = Fernet(base64.urlsafe_b64encode(old_fernet_key))

        # We will use settings.SECRET_KEY override to use model setters for the new key
        # This works because privacy_utils accesses settings.SECRET_KEY dynamically
        original_secret_key = settings.SECRET_KEY
        settings.SECRET_KEY = new_key

        try:
            # 3. Atomic Transaction for consistency
            with transaction.atomic():
                self.rotate_merchants(old_fernet)
                self.rotate_transactions(old_fernet)
                
            self.stdout.write(self.style.SUCCESS('\nKey rotation completed successfully.'))
            
        except Exception as e:
            # Revert secret key if anything fails within the transaction
            # (though the process will exit anyway)
            self.stderr.write(self.style.ERROR(f'\nCritical failure during rotation: {str(e)}'))
            raise e
        finally:
            settings.SECRET_KEY = original_secret_key

    def rotate_merchants(self, old_fernet: Fernet) -> None:
        """Rotates Merchant names and blind indexes."""
        self.stdout.write('Processing Merchants...')
        
        # We need to fetch the raw encrypted values from the DB
        # because accessing the model attribute will trigger automatic decryption
        # with the NEW key (set in handle()), which will fail.
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM api_merchant")
            merchant_data = {row[0]: row[1] for row in cursor.fetchall()}

        merchants = Merchant.objects.all().iterator()
        processed = 0
        
        for merchant in merchants:
            raw_encrypted_name = merchant_data.get(merchant.id)
            if raw_encrypted_name:
                # Decrypt with old key
                decrypted_name = old_fernet.decrypt(raw_encrypted_name.encode()).decode()
                
                # Re-encrypt and re-hash using setters (uses new SECRET_KEY via EncryptedCharField)
                merchant.name = decrypted_name
                merchant.save(update_fields=['name', 'name_hash', 'updated_at'])
            
            processed += 1
            if processed % 50 == 0:
                self.stdout.write(f'  ... {processed} merchants processed')
        
        self.stdout.write(self.style.SUCCESS(f'Finished Merchants: {processed} processed.'))

    def rotate_transactions(self, old_fernet: Fernet) -> None:
        """Rotates Transaction descriptions, amounts and blind indexes."""
        self.stdout.write('\nProcessing Transactions...')

        # Fetch raw encrypted values
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, description, amount FROM api_transaction")
            transaction_data = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
        
        transactions = Transaction.objects.all().iterator()
        processed = 0
        
        for tx in transactions:
            update_fields = ['updated_at']
            raw_desc, raw_amount = transaction_data.get(tx.id, (None, None))
            
            # Handle encrypted description and its hash
            if raw_desc:
                decrypted_desc = old_fernet.decrypt(raw_desc.encode()).decode()
                tx.description = decrypted_desc
                update_fields.extend(['description', 'description_hash'])
            
            # Handle encrypted amount
            if raw_amount:
                decrypted_amount = old_fernet.decrypt(raw_amount.encode()).decode()
                tx.amount = decrypted_amount
                update_fields.append('amount')
            
            if len(update_fields) > 1:
                tx.save(update_fields=update_fields)
            
            processed += 1
            if processed % 100 == 0:
                self.stdout.write(f'  ... {processed} transactions processed')
        
        self.stdout.write(self.style.SUCCESS(f'Finished Transactions: {processed} processed.'))
