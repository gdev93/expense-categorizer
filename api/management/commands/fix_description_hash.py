import logging

from django.core.management import BaseCommand

from api.models import Transaction
from api.privacy_utils import generate_blind_index


class Command(BaseCommand):
    help = 'Populates the Merchant fuzzy search columns for all users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username of a specific user to update (optional)',
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            help='Specific iteration chunk size (optional, default: 1000)',
            default=1000
        )
    def handle(self, *args, **options):
        main_query = Transaction.objects.all()
        username = options.get('user')
        chunk_size = options.get('chunk_size')
        if username:
            logging.info(f"Updating transactions for user {username} only.")
            main_query = main_query.filter(user__username=username)
        if chunk_size:
            chunk_size = min(chunk_size, main_query.count())
            logging.info(f"Updating transactions in chunks of size {chunk_size}.")
        transactions = []
        for tx in Transaction.objects.all().iterator(chunk_size=chunk_size):
            tx.description_hash = generate_blind_index(tx.description) if tx.description else None
            transactions.append(tx)
        Transaction.objects.bulk_update(transactions, ['description_hash'])

