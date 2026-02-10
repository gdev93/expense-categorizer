import logging
import time

from celery import shared_task
from django.contrib.auth.models import User

from api.models import Transaction, UploadFile, Rule, Category, DefaultCategory
from processors.expense_upload_processor import ExpenseUploadProcessor

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
    try:
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
