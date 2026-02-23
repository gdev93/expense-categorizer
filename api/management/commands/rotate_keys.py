import os
import hashlib
import hmac
import base64
from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings
from api.models import Merchant, Transaction

class Command(BaseCommand):
    help = 'Rotates cryptographic keys for Merchant and Transaction models.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--rotate',
            action='store_true',
            help='Explicitly allow key rotation.',
        )

    def handle(self, *args, **options):
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

    def rotate_merchants(self, old_fernet):
        """Rotates Merchant names and blind indexes."""
        self.stdout.write('Processing Merchants...')
        
        merchants = Merchant.objects.all().iterator()
        processed = 0
        
        for merchant in merchants:
            if merchant.encrypted_name:
                # Decrypt with old key
                decrypted_name = old_fernet.decrypt(merchant.encrypted_name.encode()).decode()
                
                # Re-encrypt and re-hash using setters (uses new SECRET_KEY)
                merchant.name = decrypted_name
                merchant.save(update_fields=['encrypted_name', 'name_hash', 'updated_at'])
            
            processed += 1
            if processed % 50 == 0:
                self.stdout.write(f'  ... {processed} merchants processed')
        
        self.stdout.write(self.style.SUCCESS(f'Finished Merchants: {processed} processed.'))

    def rotate_transactions(self, old_fernet):
        """Rotates Transaction descriptions, amounts and blind indexes."""
        self.stdout.write('\nProcessing Transactions...')
        
        transactions = Transaction.objects.all().iterator()
        processed = 0
        
        for tx in transactions:
            update_fields = ['updated_at']
            
            # Handle encrypted description and its hash
            if tx.encrypted_description:
                decrypted_desc = old_fernet.decrypt(tx.encrypted_description.encode()).decode()
                tx.description = decrypted_desc
                update_fields.extend(['encrypted_description', 'description_hash'])
            
            # Handle encrypted amount
            if tx.encrypted_amount:
                decrypted_amount = old_fernet.decrypt(tx.encrypted_amount.encode()).decode()
                tx.amount = decrypted_amount
                update_fields.append('encrypted_amount')
            
            if len(update_fields) > 1:
                tx.save(update_fields=update_fields)
            
            processed += 1
            if processed % 100 == 0:
                self.stdout.write(f'  ... {processed} transactions processed')
        
        self.stdout.write(self.style.SUCCESS(f'Finished Transactions: {processed} processed.'))
