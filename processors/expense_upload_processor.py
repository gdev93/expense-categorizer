import os

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, TransactionCategorization
from api.models import Transaction, Category, Merchant, CsvUpload
from processors.data_prechecks import parse_raw_transaction, RawTransactionParseResult
from processors.parser_utils import normalize_amount, parse_raw_date, parse_amount_from_raw_data_without_suggestion, \
    parse_date_from_raw_data_with_no_suggestions


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

def _create_uncategorized_transaction(user: User, transaction_parse_result: RawTransactionParseResult) -> Transaction:
    """
    Create an uncategorized transaction.
    """
    return Transaction(
        user=user,
        raw_data=transaction_parse_result.raw_data,
        amount=abs(transaction_parse_result.amount),
        original_amount=transaction_parse_result.original_amount,
        transaction_date=transaction_parse_result.date,
        original_date=transaction_parse_result.date_original,
        description=transaction_parse_result.description
    )


def _create_categorized_transaction(
        user: User,
        transaction_parse_result: RawTransactionParseResult,
        reference_transaction: Transaction
) -> Transaction:
    """
    Create a categorized transaction based on a reference transaction.
    """
    return Transaction(
        user=user,
        raw_data=transaction_parse_result.raw_data,
        merchant=reference_transaction.merchant,
        merchant_raw_name=reference_transaction.merchant_raw_name or reference_transaction.merchant.normalized_name,
        category=reference_transaction.category,
        transaction_date=transaction_parse_result.date,
        amount=abs(transaction_parse_result.amount),
        original_amount=transaction_parse_result.original_amount,
        original_date=transaction_parse_result.date_original,
        description=transaction_parse_result.description,
        status='categorized'
    )


def _find_reference_transaction(user: User, transaction_parse_result: RawTransactionParseResult,
                                precheck_confidence_threshold: float) -> Transaction | None:
    parse_result_merchant = transaction_parse_result.merchant
    if parse_result_merchant:
        similar_transaction_by_merchant = Transaction.objects.filter(
            Q(user=user) and (Q(merchant__name__search=parse_result_merchant) | Q(
                merchant__normalized_name__search=parse_result_merchant) | Q(
                merchant__name__search=parse_result_merchant))).first()
        if similar_transaction_by_merchant:
            return similar_transaction_by_merchant
    sql = """
          SELECT t.*,
                 WORD_SIMILARITY(t.description, %s) AS description_similarity
          FROM api_transaction t
          WHERE t.status = 'categorized'
            AND t.merchant_id IS NOT NULL
            AND t.user_id = %s
            AND WORD_SIMILARITY(t.description, %s) >= %s
          ORDER BY description_similarity DESC, t.updated_at DESC LIMIT 1
          """

    params = [
        transaction_parse_result.description,
        user.id,
        transaction_parse_result.description,
        precheck_confidence_threshold
    ]

    try:
        return Transaction.objects.raw(sql, params)[0]
    except IndexError:
        return None


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

    def _process_prechecks(self, batch: list[RawTransactionParseResult], csv_upload: CsvUpload) -> list[Transaction]:
        all_transactions_to_upload: list[Transaction] = []
        all_transactions_categorized: list[Transaction] = []
        for transaction_parse_result in batch:
            if not transaction_parse_result.is_valid():
                all_transactions_to_upload.append(
                    Transaction(user=self.user, raw_data=transaction_parse_result.raw_data, csv_upload=csv_upload)
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
            # Try to find a matching transaction and create categorized transaction
            reference_transaction = _find_reference_transaction(self.user,
                                                                transaction_parse_result,
                                                                self.pre_check_confidence_threshold)
            if reference_transaction:
                categorized_transaction = _create_categorized_transaction(
                    self.user,
                    transaction_parse_result,
                    reference_transaction
                )
                categorized_transaction.csv_upload = csv_upload
                all_transactions_categorized.append(categorized_transaction)
            else:
                uncategorized_transaction = _create_uncategorized_transaction(self.user, transaction_parse_result)
                uncategorized_transaction.csv_upload = csv_upload
                all_transactions_to_upload.append(uncategorized_transaction)

        Transaction.objects.bulk_create(all_transactions_categorized + all_transactions_to_upload)
        print(
            f"Found {len(all_transactions_categorized)} {"👌" if len(all_transactions_categorized) > 0 else "😩"} transactions that have similar merchant names with confidence >= {self.pre_check_confidence_threshold}"
        )
        return all_transactions_to_upload

    def _process_batch(self, batch: list[RawTransactionParseResult], csv_upload: CsvUpload):
        transaction_to_upload = self._process_prechecks(batch, csv_upload)

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
                transaction_date = parse_raw_date(tx_data.date)
                amount = normalize_amount(tx_data.amount)
                original_amount = tx_data.original_amount
                description = tx_data.description
                merchant_name = tx_data.merchant
                category_name = tx_data.category
                if failure == 'true' or not merchant_name or not category_name:
                    print(f"Transaction from agent {tx_data} has failed")
                    Transaction.objects.filter(id=tx_id).update(status='uncategorized', failure_code=1)
                    continue

                merchant = Merchant.objects.filter(name__icontains=merchant_name.strip()).first()
                if not merchant:
                    merchant = Merchant(name=merchant_name)
                    merchant.save()


                category = Category.objects.filter(name__icontains=category_name.strip(), user=self.user).first()
                if not category:
                    print(f"Agent response {tx_data} did not use the list of categories given by the user. Set transaction uncategorized.")
                    Transaction.objects.filter(id=tx_id).update(status='uncategorized', failure_code=1)
                    continue

                # Create transaction
                updated_count = Transaction.objects.filter(id=tx_id, user=self.user).update(
                    transaction_date=transaction_date,
                    amount=abs(amount),
                    original_amount=original_amount,
                    description=description,
                    merchant=merchant,
                    merchant_raw_name=merchant_name,
                    category=category,
                    original_date=tx_data.date,
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

    def process_transactions(self, raw_transaction: list[dict[str, str]]) -> CsvUpload:
        all_csv_uploads = list(CsvUpload.objects.filter(user=self.user))
        transactions_parsed = parse_raw_transaction(raw_transaction, all_csv_uploads)
        data_count = len(transactions_parsed)
        batch_size = self.batch_helper.compute_batch_size(data_count)

        total_batches = (data_count + batch_size - 1) // batch_size

        print(f"\n{'=' * 60}")
        print(f"🚀 Starting CSV Processing: {data_count} transactions")
        print(f"{'=' * 60}\n")
        csv_upload = CsvUpload.objects.create(user=self.user)
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = start_idx + batch_size
            batch = transactions_parsed[start_idx:end_idx]
            with transaction.atomic():
                self._process_batch(batch, csv_upload)
        complete_categorized_transaction = Transaction.objects.filter(user=self.user, csv_upload=csv_upload,
                                                                      status='categorized',
                                                                      original_amount__isnull=False,
                                                                      description__isnull=False,
                                                                      original_date__isnull=False).first()
        if complete_categorized_transaction:
            for key, value in complete_categorized_transaction.raw_data.items():
                if value == complete_categorized_transaction.original_amount:
                    csv_upload.amount_column_name = key
                elif value == complete_categorized_transaction.original_date:
                    csv_upload.date_column_name = key
                elif value == complete_categorized_transaction.description:
                    csv_upload.description_column_name = key
                elif value == complete_categorized_transaction.merchant_raw_name:
                    csv_upload.merchant_column_name = key

            csv_upload.save()
        uncategorized_transactions = Transaction.objects.filter(user=self.user, csv_upload=csv_upload,status__in=['uncategorized', 'pending'])
        for uncategorized_transaction in uncategorized_transactions:
            original_amount = uncategorized_transaction.raw_data.get(csv_upload.amount_column_name, '')
            if not original_amount:
                parsed_amount_result = parse_amount_from_raw_data_without_suggestion(uncategorized_transaction.raw_data)
                if parsed_amount_result.is_valid():
                    for column_name, amount_finding in parsed_amount_result.fields.items():
                        if column_name in uncategorized_transaction.raw_data:
                            original_amount = uncategorized_transaction.raw_data[column_name]
                            if original_amount!=amount_finding.original_value:
                                continue
                            uncategorized_transaction.original_amount = original_amount
                            uncategorized_transaction.amount = abs(amount_finding.amount)
                            break

            description = uncategorized_transaction.raw_data.get(csv_upload.description_column_name, '')
            merchant = uncategorized_transaction.raw_data.get(csv_upload.merchant_column_name, '')
            original_date = uncategorized_transaction.raw_data.get(csv_upload.date_column_name, '')
            if not original_date:
                date, original_date_column_name = parse_date_from_raw_data_with_no_suggestions(uncategorized_transaction.raw_data)
                if date:
                    uncategorized_transaction.transaction_date = date
                    uncategorized_transaction.original_date = original_date
            amount = normalize_amount(original_amount)
            transaction_date = parse_raw_date(original_date)
            uncategorized_transaction.transaction_date = transaction_date
            uncategorized_transaction.amount = abs(amount)
            uncategorized_transaction.original_amount = original_amount
            uncategorized_transaction.description = description
            uncategorized_transaction.merchant_raw_name = merchant
            uncategorized_transaction.original_date = original_date
        Transaction.objects.bulk_update(uncategorized_transactions, ['transaction_date', 'amount', 'original_amount', 'description', 'merchant_raw_name', 'original_date'])
        return csv_upload
