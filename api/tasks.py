import itertools
import logging
import os
import random
import time

from celery import shared_task
from django.contrib.auth.models import User

from api.models import Transaction, UploadFile, Rule, Category, DefaultCategory, Merchant
from processors.data_prechecks import parse_raw_transaction
from processors.expense_upload_processor import ExpenseUploadProcessor
from processors.transaction_updater import TransactionUpdater

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=2,
    acks_late=True,
    name='api.tasks.process_upload'
)
def process_upload(self, user_id: int, upload_file_id: int):
    logger.info(f"Processing upload {upload_file_id} for user {user_id}")
    start_time = time.time()
    upload_file = UploadFile.objects.get(id=upload_file_id)
    upload_file.status = 'processing'
    upload_file.save()
    user = User.objects.get(id=user_id)
    transactions = Transaction.objects.filter(upload_file=upload_file, user=user, status='pending')
    if not transactions.exists():
        upload_file.status = 'completed'
        upload_file.save()
        return

    user_rules = list(
        Rule.objects.filter(
            user=user,
            is_active=True
        ).values_list('text_content', flat=True)
    )
    user_categories = Category.objects.filter(user=user)
    if not user_categories.exists():
        for default_category in DefaultCategory.objects.all():
            category = Category(user=user, name=default_category.name, description=default_category.description,
                                is_default=True)
            category.save()
    is_simulation = os.getenv('ENABLE_CATEGORIZATION_SIMULATION', 'false').lower() == 'true'
    try:
        if is_simulation:
            logger.info(f"Simulating categorization for upload {upload_file_id} for user {user_id}")
            available_categories = list(Category.objects.filter(user=user))
            if not available_categories:
                for default_category in DefaultCategory.objects.all():
                    category = Category(user=user, name=default_category.name, description=default_category.description,
                                        is_default=True)
                    category.save()
                available_categories = list(Category.objects.filter(user=user))

            demo_merchant, _ = Merchant.objects.get_or_create(name="Demo Merchant", user=user)
            total_count = transactions.count()
            # Process in roughly 5 batches for progress visualization
            chunk_size = max(1, total_count // 5)
            iterator = transactions.iterator()
            
            while True:
                chunk = list(itertools.islice(iterator, chunk_size))
                if not chunk:
                    break
                
                for tx in chunk:
                    res = parse_raw_transaction(tx.raw_data, [upload_file])
                    if res.is_income:
                        TransactionUpdater.update_income_transaction(tx, res)
                    else:
                        TransactionUpdater.update_transaction_with_parse_result(tx, res)
                        tx.category = random.choice(available_categories) if available_categories else None
                        tx.merchant = demo_merchant
                        tx.status = 'categorized'
                    tx.save()
                
                time.sleep(1) # Simulated delay
            
            processing_time = int((time.time() - start_time) * 1000)
            upload_file.processing_time = processing_time
            upload_file.status = 'completed'
        else:
            processor = ExpenseUploadProcessor(
                user=user,
                user_rules=user_rules,
                available_categories=list(
                    Category.objects.filter(user=user)
                )
            )
            logging.info(f"{user}'s data {upload_file.file_name} is being processed.")
            upload_file = processor.process_transactions(transactions.iterator(), upload_file)
            processing_time = int((time.time() - start_time) * 1000)
            upload_file.processing_time = processing_time
    except Exception as e:
        logger.error(f"Attempt {self.request.retries} failed for file {upload_file_id}: {e}")
        if self.request.retries >= self.max_retries:
            upload_file.status = 'failed'
            upload_file.save()
        raise e

    upload_file.save()
