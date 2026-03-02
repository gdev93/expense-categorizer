import itertools
import logging
import os
import random
import time

from celery import shared_task
from django.contrib.auth.models import User

from api.models import Transaction, UploadFile, Rule, Category, DefaultCategory, Merchant
from api.services import RollupService, ForecastService
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

    years_months = Transaction.objects.filter(upload_file=upload_file, user=user).values_list('transaction_date__year', 'transaction_date__month').distinct()
    RollupService.update_all_rollups(user, years_months)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=2,
    acks_late=True,
    name='api.tasks.delete_user_data'
)
def delete_user_data(self, user_id: int):
    logger.info(f"Deleting user data for user {user_id}")
    user = User.objects.get(id=user_id)
    user.delete()
    logger.info(
        f"User data for user {user_id} deleted successfully"
    )

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=2,
    acks_late=True,
    name='api.tasks.populate_rollups'
)
def populate_rollups(self):
    logger.info("Starting rollup population task")

    # Filter users
    users = User.objects.filter(profile__needs_rollup_recomputation=True)

    total_users = users.count()
    logger.info(f'Processing {total_users} user(s)...')

    for user_idx, user in enumerate(users, 1):
        logger.info(f'[{user_idx}/{total_users}] Processing user: {user.username}')

        # Get all years with transactions for this user
        years_months = Transaction.objects.filter(user=user).values_list(
            'transaction_date__year',
            'transaction_date__month'
        ).distinct()

        years_months = [(y, m) for y, m in years_months]

        if not years_months:
            logger.warning(f'  No transactions found for {user.username}')
            continue

        # Extract unique years
        years = set(y for y, m in years_months if y is not None)

        logger.info(f'  Found transactions in years: {sorted(years)}')
        logger.info(f'  Updating {len(years_months)} year-month combinations...')

        try:
            RollupService.update_all_rollups(user, list(years_months))
            logger.info(f'  ✓ Successfully updated rollups for {user.username}')
        except Exception as e:
            logger.error(f'  ✗ Error updating rollups for {user.username}: {str(e)}')
            if self.request.retries >= self.max_retries:
                raise e

    logger.info('Rollup population completed!')


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=2,
    acks_late=True,
    name='api.tasks.populate_category_rollups'
)
def populate_category_rollups(self):
    logger.info("Starting category rollup population task")

    users = User.objects.filter(profile__needs_rollup_recomputation=True)
    total_users = users.count()
    logger.info(f'Processing {total_users} user(s) for category rollups...')

    for user_idx, user in enumerate(users, 1):
        logger.info(f'[{user_idx}/{total_users}] Processing category rollups for user: {user.username}')

        years_months = Transaction.objects.filter(user=user).values_list(
            'transaction_date__year',
            'transaction_date__month'
        ).distinct()

        years_months = [(y, m) for y, m in years_months if y is not None]

        if not years_months:
            continue

        try:
            RollupService.update_category_rollup(user, years_months)
            from api.models import Profile
            Profile.objects.filter(user=user).update(needs_rollup_recomputation=False)
            logger.info(f'  ✓ Successfully updated category rollups for {user.username}')
        except Exception as e:
            logger.error(f'  ✗ Error updating category rollups for {user.username}: {str(e)}')
            if self.request.retries >= self.max_retries:
                raise e

    logger.info('Category rollup population completed!')


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=2,
    acks_late=True,
    name='api.tasks.generate_monthly_forecasts'
)
def generate_monthly_forecasts(self) -> str:
    """
    Main task to analyze trends and pre-populate next month's budget.
    Iterates through users and categories in batches.
    """
    logger.info("Starting forecast generation task...")

    ForecastService.compute_forecast(months=[], years=[])

    return f"Forecasts completed successfully."
