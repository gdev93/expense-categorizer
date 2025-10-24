import os

from django.db import transaction
from django.db.models import Count

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, TransactionCategorization
from api.models import Transaction, Category, Merchant
from processors.data_prechecks import parse_raw_transaction
from processors.parser_utils import _parse_date, normalize_amount


def _calculate_statistics(transactions: list[dict], results: list[dict]) -> dict:
    """
    Calculate processing statistics.

    Args:
        transactions: Original transaction list
        results: Batch processing results

    Returns:
        dictionary with statistics
    """
    total = len(transactions)
    successful_batches = sum(1 for r in results if r.get('success', False))
    total_batches = len(results)
    total_categorized = sum(len(r.get('categorizations', {})) for r in results)
    total_persisted = sum(r.get('persisted_count', 0) for r in results)

    return {
        'total': total,
        'successful_batches': successful_batches,
        'total_batches': total_batches,
        'total_categorized': total_categorized,
        'total_persisted': total_persisted
    }


class ExpenseUploadProcessor:
    """
    Handles the processing and persistence of uploaded expense transactions.

    Responsibilities:
    - Batch processing through agent
    - Persistence of results
    - Progress tracking and logging
    """
    pre_check_confidence_threshold = os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', 0.8)

    def __init__(self, user, batch_size: int = 5, user_rules: list[str] = None,
                 available_categories: list[str] | None = None):
        """
        Args:
            user: Django user object
            batch_size: Number of transactions per batch
            user_rules: List of user-defined categorization rules
        """
        self.user = user
        self.batch_size = batch_size
        self.agent = ExpenseCategorizerAgent(user_rules=user_rules, available_categories=available_categories)

    def process_transactions(self, raw_transaction: list[dict[str, str]]):
        transactions_parsed = parse_raw_transaction(raw_transaction)
        all_transactions_to_upload: list[dict[str, str]] = []
        all_transactions_categorized: list[Transaction] = []
        for transaction_parse_result in transactions_parsed:
            if not transaction_parse_result.is_valid():
                all_transactions_to_upload.append(transaction_parse_result.raw_data)
                continue
            # find transaction that has a merchant_raw_name that has great word similarity
            sql = """
                  SELECT t.*,
                         WORD_SIMILARITY(m.name, %s) AS similarity
                  FROM api_transaction t
                           INNER JOIN api_merchant m ON t.merchant_id = m.id
                  WHERE t.status = 'categorized'
                    AND t.merchant_id IS NOT NULL
                    AND t.user_id = %s
                    AND WORD_SIMILARITY(m.name, %s) >= %s
                  ORDER BY similarity DESC LIMIT 1
                  """

            # Execute with parameters
            params = [
                transaction_parse_result.description,  # For first WORD_SIMILARITY
                self.user.id,  # For user_id
                transaction_parse_result.description,  # For second WORD_SIMILARITY
                self.pre_check_confidence_threshold  # For threshold
            ]

            try:
                similar_transaction = Transaction.objects.raw(sql, params)[0]
                if similar_transaction:
                    new_categorized_transaction = Transaction(
                        user=self.user,
                        raw_data=transaction_parse_result.raw_data,
                        merchant=similar_transaction.merchant,
                        merchant_raw_name=similar_transaction.merchant_raw_name,
                        category=similar_transaction.category,
                        transaction_date=transaction_parse_result.date,
                        amount=transaction_parse_result.amount,
                        original_amount=transaction_parse_result.original_amount,
                        description=transaction_parse_result.description,
                        status='categorized'
                    )
                    all_transactions_categorized.append(new_categorized_transaction)
                else:
                    all_transactions_to_upload.append(transaction_parse_result.raw_data)
            except IndexError:
                all_transactions_to_upload.append(transaction_parse_result.raw_data)

        Transaction.objects.bulk_create(all_transactions_categorized)
        print(
            f"Found {len(all_transactions_categorized)} transactions that have similar merchant names with confidence >= {self.pre_check_confidence_threshold} 👌"
        )

        total_batches = (len(all_transactions_to_upload) + self.batch_size - 1) // self.batch_size

        print(f"\n{'=' * 60}")
        print(f"🚀 Starting CSV Processing: {len(raw_transaction)} transactions")
        print(f"{'=' * 60}\n")

        with transaction.atomic():
            for batch_num in range(total_batches):
                start_idx = batch_num * self.batch_size
                end_idx = start_idx + self.batch_size
                batch = raw_transaction[start_idx:end_idx]
                all_pending_transactions = [Transaction(user=self.user, raw_data=tx) for tx in batch]
                Transaction.objects.bulk_create(all_pending_transactions)
                agent_upload_transaction = [AgentTransactionUpload(transaction_id=tx.id, raw_text=tx.raw_data) for tx in
                                            all_pending_transactions]
                batch_result = self.agent.process_batch(agent_upload_transaction)

                self._persist_batch_results(batch_result)

    def _persist_batch_results(self, batch: list[TransactionCategorization]):

        existing_transactions = (Transaction.objects
                                 .values('amount', 'merchant_raw_name', 'transaction_date')  # Group by these fields
                                 .annotate(count=Count('id'))  # Count the number of transactions in each group
                                 .filter(count__gte=1)  # Keep only the groups (combinations) with a count > 1
                                 .values_list('amount', 'merchant_raw_name','transaction_date', flat=False)
                                 )
        for tx_data in batch:
            tx_id = tx_data.transaction_id
            try:
                failure = tx_data.failure
                # Extract and parse transaction data
                transaction_date = _parse_date(tx_data.date)
                amount = normalize_amount(tx_data.amount)
                original_amount = tx_data.original_amount
                description = tx_data.description
                merchant_name = tx_data.merchant
                category_name = tx_data.category
                if failure == 'true':
                    print(f"Transaction from agent {tx_data} has failed")
                    continue
                # Get or create merchant
                if merchant_name:
                    merchant, _ = Merchant.objects.get_or_create(
                        name=merchant_name
                    )
                else:
                    print(f"Merchant name in {tx_data} is not known")
                    continue

                if (amount, merchant_name, transaction_date) in existing_transactions:
                    continue
                # Get or create category
                category = None
                if category_name:
                    category, _ = Category.objects.get_or_create(
                        name=category_name,
                        user=self.user
                    )
                else:
                    Category.objects.create(name='altro', user=self.user, defaults={'is_default': False}).save()
                # Create transaction
                updated_count = Transaction.objects.filter(id=tx_id, user=self.user).update(
                    transaction_date=transaction_date,
                    amount=amount,
                    original_amount=original_amount,
                    description=description,
                    merchant=merchant,
                    merchant_raw_name=merchant_name,
                    category=category,
                    status='categorized' if not failure else 'uncategorized',
                    confidence_score=None,
                    modified_by_user=False,
                    failure_code=0 if not failure else 1
                )

                if updated_count == 0:
                    print(f"⚠️ Transaction {tx_id} not found or doesn't belong to user")


            except Exception as e:
                print(f"⚠️  Failed to persist transaction {tx_id}: {str(e)}")
                continue