import os

from django.contrib.auth.models import User
from django.db import transaction

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, TransactionCategorization
from api.models import Transaction, Category, Merchant
from processors.data_prechecks import parse_raw_transaction, RawTransactionParseResult
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


class BatchingHelper:
    batch_size = os.environ.get('AGENT_BATCH_SIZE', 15)
    batch_max_size = os.environ.get('AGENT_BATCH_MAX_SIZE', 25)
    batch_min_size = os.environ.get('AGENT_BATCH_MIN_SIZE', 10)
    def __init__(self, batch_size:int = batch_size, batch_max_size:int=batch_max_size, batch_min_size:int=batch_min_size):
        self.batch_size = batch_size
        self.batch_max_size = batch_max_size
        self.batch_min_size = batch_min_size

    def compute_batch_size(self, data_count:int) -> int:
        if data_count < self.batch_min_size:
            return self.batch_min_size
        if self.batch_size < data_count < self.batch_max_size:
            return self.batch_max_size
        return self.batch_size

class ExpenseUploadProcessor:
    """
    Handles the processing and persistence of uploaded expense transactions.

    Responsibilities:
    - Batch processing through agent
    - Persistence of results
    - Progress tracking and logging
    """
    pre_check_confidence_threshold = os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', 0.8)


    def __init__(self, user: User, user_rules: list[str] = None, available_categories: list[str] | None = None, batch_helper:BatchingHelper | None = None):
        self.user = user
        self.batch_helper = batch_helper or BatchingHelper()
        self.agent = ExpenseCategorizerAgent(user_rules=user_rules, available_categories=available_categories)

    def _process_prechecks(self, batch: list[RawTransactionParseResult]) -> list[Transaction]:
        all_transactions_to_upload: list[Transaction] = []
        all_transactions_categorized: list[Transaction] = []
        for transaction_parse_result in batch:
            if not transaction_parse_result.is_valid():
                all_transactions_to_upload.append(
                    Transaction(user=self.user, raw_data=transaction_parse_result.raw_data)
                )
                continue
            if transaction_parse_result.amount > 0:
                print(f"Only expenses are allowed, skipping transaction {transaction_parse_result.raw_data}")
                continue
            if transaction_parse_result.description:
                transaction_from_description = Transaction.objects.filter(
                    user=self.user,
                    description=transaction_parse_result.description,
                ).exists()
                if transaction_from_description:
                    print(f"Transaction from description {transaction_parse_result.description} already categorized")
                    continue

            # find transaction that has a merchant_raw_name that has great word similarity
            # raw sql because word similarity does not work if the first item is not the merchant name, and django builtins do not allow to change the order of parameters
            sql = """
                  SELECT t.*,
                         WORD_SIMILARITY(t.description, %s) AS description_similarity
                  FROM api_transaction t
                           INNER JOIN api_merchant m ON t.merchant_id = m.id
                  WHERE t.status = 'categorized'
                    AND t.merchant_id IS NOT NULL
                    AND t.user_id = %s
                    AND WORD_SIMILARITY(t.description, %s) >= %s
                  ORDER BY description_similarity DESC, t.updated_at DESC
                  LIMIT 1
                  """

            # Execute with parameters
            params = [
                transaction_parse_result.description, # For first WORD_SIMILARITY
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
                        amount=abs(transaction_parse_result.amount),
                        original_amount=transaction_parse_result.original_amount,
                        description=transaction_parse_result.description,
                        status='categorized'
                    )
                    all_transactions_categorized.append(new_categorized_transaction)
                else:
                    all_transactions_to_upload.append(
                        Transaction(user=self.user, raw_data=transaction_parse_result.raw_data))
            except IndexError:
                all_transactions_to_upload.append(
                    Transaction(
                        user=self.user, raw_data=transaction_parse_result.raw_data,
                        amount=abs(transaction_parse_result.amount), transaction_date=transaction_parse_result.date,
                        description=transaction_parse_result.description
                    )
                )

        Transaction.objects.bulk_create(all_transactions_categorized + all_transactions_to_upload)
        print(
            f"Found {len(all_transactions_categorized)} {"👌" if len(all_transactions_categorized) > 0 else "😩"} transactions that have similar merchant names with confidence >= {self.pre_check_confidence_threshold}"
        )
        return all_transactions_to_upload

    def _process_batch(self, batch: list[RawTransactionParseResult]):
        transaction_to_upload = self._process_prechecks(batch)

        agent_upload_transaction = [AgentTransactionUpload(transaction_id=tx.id, raw_text=tx.raw_data) for tx in
                                    transaction_to_upload]
        if agent_upload_transaction:
            batch_result = self.agent.process_batch(agent_upload_transaction)
            self._persist_batch_results(batch_result)

    def _persist_batch_results(self, batch: list[TransactionCategorization]):
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
                    Transaction.objects.filter(id=tx_id, user=self.user, status='uncategorized').update()
                    continue
                # Get or create merchant
                if merchant_name:
                    merchant, _ = Merchant.objects.get_or_create(
                        name=merchant_name
                    )
                else:
                    print(f"Merchant name in {tx_data} is not known")
                    Transaction.objects.filter(id=tx_id, user=self.user).update(
                        merchant=None,
                        merchant_raw_name=None,
                        status='uncategorized'
                    )
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
                    amount=abs(amount),
                    original_amount=original_amount,
                    description=description,
                    merchant=merchant,
                    merchant_raw_name=merchant_name,
                    category=category,
                    status='categorized',
                    confidence_score=None,
                    modified_by_user=False,
                    failure_code=0 if not failure else 1
                )

                if updated_count == 0:
                    print(f"⚠️ Transaction {tx_id} not found or doesn't belong to user")


            except Exception as e:
                print(f"⚠️  Failed to persist transaction {tx_id}: {str(e)}")
                continue

    def process_transactions(self, raw_transaction: list[dict[str, str]]):
        transactions_parsed = parse_raw_transaction(raw_transaction)
        data_count = len(transactions_parsed)
        batch_size = self.batch_helper.compute_batch_size(data_count)

        total_batches = (data_count + batch_size - 1) // batch_size

        print(f"\n{'=' * 60}")
        print(f"🚀 Starting CSV Processing: {data_count} transactions")
        print(f"{'=' * 60}\n")

        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = start_idx + batch_size
            batch = transactions_parsed[start_idx:end_idx]
            with transaction.atomic():
                self._process_batch(batch)