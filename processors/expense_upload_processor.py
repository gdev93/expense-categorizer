import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction, connections

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, TransactionCategorization, GeminiResponse
from api.models import Transaction, Category, Merchant, CsvUpload, normalize_string
from processors.data_prechecks import parse_raw_transaction, RawTransactionParseResult
from processors.parser_utils import normalize_amount, parse_raw_date, parse_date_from_raw_data_with_no_suggestions
from processors.similarity_matcher import SimilarityMatcher
from processors.transaction_updater import TransactionUpdater
from processors.csv_structure_detector import CsvStructureDetector
from processors.batching_helper import BatchingHelper
from costs.services import CostService

logger = logging.getLogger(__name__)


class ExpenseUploadProcessor:
    """
    Handles the processing and persistence of uploaded expense transactions.

    Responsibilities:
    - Batch processing through agent
    - Persistence of results
    - Progress tracking and logging
    """
    pre_check_confidence_threshold = os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', 0.85)
    csv_structure_sample_size_percentage = os.environ.get('CSV_STRUCTURE_SAMPLE_SIZE_PERCENTAGE', 0.1)
    csv_structure_min_threshold = os.environ.get('CSV_STRUCTURE_MIN_THRESHOLD', 30)


    def __init__(self, user: User, user_rules: list[str] = None, available_categories: list[Category] | None = None, batch_helper:BatchingHelper | None = None):
        self.user = user
        self.batch_helper = batch_helper or BatchingHelper()
        self.agent = ExpenseCategorizerAgent(user_rules=user_rules, available_categories=available_categories)
        self.similarity_matcher = SimilarityMatcher(user, float(self.pre_check_confidence_threshold))
        self.csv_structure_detector = CsvStructureDetector(
            user,
            self.agent,
            int(self.csv_structure_min_threshold),
            float(self.csv_structure_sample_size_percentage)
        )

    def _process_prechecks(self, batch: list[Transaction], csv_upload: CsvUpload) -> list[Transaction]:
        all_transactions_to_upload: list[Transaction] = []
        all_transactions_categorized: list[Transaction] = []
        all_transactions_to_delete: list[Transaction] = []
        merchant_with_category: dict[str, tuple[Merchant, Category]] = {}
        for tx in batch:
            transaction_parse_result = parse_raw_transaction(tx.raw_data, [csv_upload])
            if not transaction_parse_result.is_valid():
                all_transactions_to_upload.append(tx)
                continue
            if transaction_parse_result.is_income:
                tx.transaction_type = 'income'
                tx.status = 'categorized'
                tx.transaction_date = transaction_parse_result.date
                tx.original_amount = transaction_parse_result.original_amount
                tx.description = transaction_parse_result.description
                tx.normalized_description = normalize_string(transaction_parse_result.description)
                tx.original_date = transaction_parse_result.date_original
                tx.amount = transaction_parse_result.amount
                tx.operation_type = transaction_parse_result.operation_type
                # income transactions are not categorized yet
                all_transactions_categorized.append(tx)
                continue
            if transaction_parse_result.description:
                transaction_from_description = Transaction.objects.filter(
                    user=self.user,
                    normalized_description=normalize_string(transaction_parse_result.description),
                    transaction_date=transaction_parse_result.date,
                ).exists()
                if transaction_from_description:
                    logger.info(f"Transaction from description {transaction_parse_result.description} already categorized")
                    all_transactions_to_delete.append(tx)
                    continue
            if transaction_parse_result.merchant and merchant_with_category.get(transaction_parse_result.merchant.name):
                merchant, category = merchant_with_category[transaction_parse_result.merchant.name]
                categorized_transaction = TransactionUpdater.update_categorized_transaction_with_category_merchant(tx, category, merchant,
                                                                                                 transaction_parse_result)
                all_transactions_categorized.append(categorized_transaction)
            else:
                reference_transaction = self.similarity_matcher.find_reference_transaction_from_raw(
                                                                             transaction_parse_result)
                if reference_transaction:
                    categorized_transaction = TransactionUpdater.update_categorized_transaction(
                        tx,
                        transaction_parse_result,
                        reference_transaction
                    )
                    all_transactions_categorized.append(categorized_transaction)
                    merchant_with_category[categorized_transaction.merchant.name] = categorized_transaction.merchant, categorized_transaction.category
                else:
                    uncategorized_transaction = TransactionUpdater.update_transaction_with_parse_result(tx, transaction_parse_result)
                    all_transactions_to_upload.append(uncategorized_transaction)

        Transaction.objects.bulk_update(all_transactions_categorized + all_transactions_to_upload,
                                        ['status', 'merchant', 'merchant_raw_name', 'category', 'transaction_date',
                                         'original_date', 'description', 'amount', 'original_amount',
                                         'transaction_type', 'normalized_description','operation_type'])
        Transaction.objects.filter(user=self.user, id__in=[tx.id for tx in all_transactions_to_delete]).delete()
        logger.info(
            f"Found {len(all_transactions_categorized)} {'👌' if len(all_transactions_categorized) > 0 else '😩'} transactions that have similar merchant names"
        )
        return all_transactions_to_upload

    def process_with_agent(self, batch: list[Transaction], csv_upload: CsvUpload) -> tuple[list[TransactionCategorization], GeminiResponse | None]:
        agent_upload_transaction = [AgentTransactionUpload(transaction_id=tx.id, raw_text=tx.raw_data) for tx in
                                    batch]
        if agent_upload_transaction:
            try:
                return self.agent.process_batch(agent_upload_transaction, csv_upload)
            except Exception as e:
                logger.error(f"⚠️  Agent failed to process batch: {str(e)}")
                return [], None
            finally:
                connections.close_all()
        return [], None

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
                    Transaction.objects.filter(id=tx_id).update(status='uncategorized', failure_code=1)
                    continue

                similar_transaction = self.similarity_matcher.find_similar_transaction_by_merchant(merchant_name=merchant_name)
                if not similar_transaction:
                    merchant, _ = Merchant.objects.get_or_create(name=merchant_name, user=self.user)
                    category = Category.objects.filter(name__icontains=category_name.strip(), user=self.user).first()
                    if not category:
                        Transaction.objects.filter(id=tx_id).update(status='uncategorized', failure_code=1, merchant=merchant)
                        continue
                else:
                    merchant = similar_transaction.merchant
                    category = similar_transaction.category

                # safety check
                transaction_from_agent = Transaction.objects.filter(user=self.user,
                                                                   id=tx_id).first() or Transaction.objects.filter(
                    user=self.user, description=description).first()
                transaction_from_agent.category = category
                transaction_from_agent.merchant = merchant
                transaction_from_agent.merchant_raw_name = merchant_name
                transaction_from_agent.original_date = tx_data.date if not transaction_from_agent.original_date else transaction_from_agent.original_date
                transaction_from_agent.original_amount = original_amount if not transaction_from_agent.original_amount else transaction_from_agent.original_amount
                transaction_from_agent.transaction_date = transaction_date if not transaction_from_agent.transaction_date else transaction_from_agent.transaction_date
                transaction_from_agent.amount = abs(
                    amount) if not transaction_from_agent.amount else transaction_from_agent.amount
                transaction_from_agent.status = 'categorized'
                transaction_from_agent.modified_by_user = False
                transaction_from_agent.failure_code = 0 if not failure else 1
                transaction_from_agent.description = tx_data.description if not transaction_from_agent.description else transaction_from_agent.description
                transaction_from_agent.normalized_description = normalize_string(transaction_from_agent.description)
                transaction_from_agent.categorized_by_agent = True
                transaction_from_agent.reasoning = tx_data.reasoning
                transaction_from_agent.save()

            except Exception as e:
                logger.error(f"⚠️  Failed to persist transaction {tx_id}: {str(e)}")
                continue
    def process_transactions(self, transactions: list[Transaction], csv_upload: CsvUpload) -> CsvUpload:

        self.csv_structure_detector.setup_csv_upload_structure(transactions, csv_upload)

        all_transactions_to_upload = self._process_prechecks(transactions, csv_upload)
        transaction_batches = self.batch_helper.compute_batches(all_transactions_to_upload)
        data_count = len(all_transactions_to_upload)

        logger.info(f"🚀 Starting CSV Processing: {data_count} transactions")

        with ThreadPoolExecutor() as executor:
            # Parallelize the agent calls only
            results = list(executor.map(lambda batch: self.process_with_agent(batch, csv_upload), transaction_batches))

        # Process each batch's results synchronously
        for batch_result, response in results:
            if response:
                CostService.log_api_usage(
                    user=self.user,
                    llm_model=response.model_name,
                    input_tokens=response.prompt_tokens,
                    output_tokens=response.candidate_tokens,
                    csv_upload=csv_upload
                )
            if batch_result:
                with transaction.atomic():
                    self._persist_batch_results(batch_result)

        with transaction.atomic():
            self._post_process_transactions(csv_upload)

        return csv_upload

    def _post_process_transactions(self, csv_upload: CsvUpload) -> None:
        """Post-process transactions after batch processing to identify column mappings and categorize uncategorized transactions."""
        self._categorize_remaining_transactions(csv_upload)

    def _categorize_remaining_transactions(self, csv_upload: CsvUpload) -> None:
        """Process uncategorized transactions by parsing their data and attempting to categorize them using similar transactions."""
        uncategorized_transactions = Transaction.objects.filter(
            user=self.user,
            csv_upload=csv_upload,
            status__in=['uncategorized', 'pending']
        )

        for tx in uncategorized_transactions:
            # Get values from raw_data, handling None column names
            original_amount = tx.raw_data.get(csv_upload.expense_amount_column_name, '') if csv_upload.expense_amount_column_name else '' or tx.raw_data.get(csv_upload.income_amount_column_name, '') if csv_upload.income_amount_column_name else ''
            description = tx.raw_data.get(csv_upload.description_column_name,
                                          '') if csv_upload.description_column_name else ''
            merchant = tx.raw_data.get(csv_upload.merchant_column_name, '') if csv_upload.merchant_column_name else ''
            original_date = tx.raw_data.get(csv_upload.date_column_name, '') if csv_upload.date_column_name else ''

            if original_amount:
                amount = normalize_amount(original_amount)
                tx.amount = abs(amount)
                tx.original_amount = original_amount

            if original_date:
                transaction_date = parse_raw_date(original_date)
                tx.transaction_date = transaction_date
                tx.original_date = original_date

            tx.description = description
            tx.normalized_description = normalize_string(description) if description else ''
            tx.merchant_raw_name = merchant

            # Only try to find similar transactions if we have a description
            if description:
                similar_tx = self.similarity_matcher.find_reference_transaction_from_tx(tx)
                if similar_tx:
                    tx.category = similar_tx.category
                    tx.merchant_raw_name = similar_tx.merchant_raw_name
                    tx.merchant = similar_tx.merchant
                    tx.status = 'categorized'
                else:
                    tx.status = 'uncategorized'
            else:
                tx.status = 'uncategorized'

        Transaction.objects.bulk_update(
            uncategorized_transactions,
            ['transaction_date', 'amount', 'original_amount', 'description',
             'merchant_raw_name', 'original_date', 'category', 'status', 'merchant', 'normalized_description']
        )
        Transaction.objects.filter(user=self.user, csv_upload=csv_upload, status__in=['pending', 'uncategorized'],
                                   original_amount__isnull=True).update(status='uncategorized',
                                                                        transaction_type='income')

def persist_csv_file(csv_data: list[dict[str, str]], user: User, csv_file: UploadedFile) -> CsvUpload:
    csv_upload = CsvUpload.objects.create(user=user, dimension=csv_file.size,file_name=csv_file.name)
    all_pending_transactions = [Transaction(
        csv_upload=csv_upload,
        user=user,
        status='pending',
        raw_data=csv_row,
    ) for csv_row in csv_data]
    Transaction.objects.bulk_create(all_pending_transactions)
    return csv_upload