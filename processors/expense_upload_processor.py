import logging
import os
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction, connections
from django.db.models import Count, Max

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, TransactionCategorization, GeminiResponse
from api.models import Transaction, Category, Merchant, UploadFile, normalize_string
from costs.services import CostService
from processors.batching_helper import BatchingHelper
from processors.csv_structure_detector import CsvStructureDetector
from processors.data_prechecks import parse_raw_transaction
from processors.embeddings import EmbeddingEngine
from processors.parser_utils import normalize_amount, parse_raw_date
from processors.similarity_matcher import SimilarityMatcher, generate_embedding, SimilarityMatcherRAG, is_rag_reliable
from processors.transaction_updater import TransactionUpdater

logger = logging.getLogger(__name__)


class ExpenseUploadProcessor(SimilarityMatcherRAG):
    """
    Handles the processing and persistence of uploaded expense transactions.

    Responsibilities:
    - Batch processing through agent
    - Persistence of results
    - Progress tracking and logging
    """
    pre_check_confidence_threshold = os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', 0.85)
    file_structure_sample_size_percentage = os.environ.get('CSV_STRUCTURE_SAMPLE_SIZE_PERCENTAGE', 0.1)
    file_structure_min_threshold = os.environ.get('CSV_STRUCTURE_MIN_THRESHOLD', 30)


    def __init__(self, user: User, user_rules: list[str] = None, available_categories: list[Category] | None = None, batch_helper:BatchingHelper | None = None):
        self.user = user
        self.batch_helper = batch_helper or BatchingHelper()
        self.agent = ExpenseCategorizerAgent(user_rules=user_rules, available_categories=available_categories)
        self.similarity_matcher = SimilarityMatcher(user, float(self.pre_check_confidence_threshold))
        self.file_structure_detector = CsvStructureDetector(
            user,
            self.agent,
            int(self.file_structure_min_threshold),
            float(self.file_structure_sample_size_percentage)
        )

    def process_transactions(self, transactions: list[Transaction], upload_file: UploadFile) -> UploadFile:

        self.file_structure_detector.setup_upload_file_structure(transactions, upload_file)

        all_transactions_to_upload = self._process_prechecks(transactions, upload_file)
        transaction_batches = self.batch_helper.compute_batches(all_transactions_to_upload)
        data_count = len(all_transactions_to_upload)

        logger.info(f"🚀 Starting CSV Processing: {data_count} transactions")

        with ThreadPoolExecutor() as executor:
            # Parallelize the agent calls only
            results = list(executor.map(lambda batch: self._process_with_agent(batch, upload_file), transaction_batches))

        # Process each batch's results synchronously
        for batch_result, response in results:
            if response:
                CostService.log_api_usage(
                    user=self.user,
                    llm_model=response.model_name,
                    input_tokens=response.prompt_tokens,
                    output_tokens=response.candidate_tokens,
                    number_of_transactions = len(batch_result),
                    upload_file=upload_file
                )
            if batch_result:
                with transaction.atomic():
                    self._persist_batch_results(batch_result)

        with transaction.atomic():
            self._post_process_transactions(upload_file)
            upload_file.status = 'completed'
            upload_file.save()

        return upload_file
    def _process_prechecks(self, batch: list[Transaction], upload_file: UploadFile) -> list[Transaction]:
        all_transactions_to_upload: list[Transaction] = []
        all_transactions_as_income: list[Transaction] = []
        all_transactions_categorized: list[Transaction] = []
        all_transactions_to_delete: list[Transaction] = []
        merchant_with_category: dict[str, tuple[Merchant, Category]] = {}
        for tx in batch:
            transaction_parse_result = parse_raw_transaction(tx.raw_data, [upload_file])
            if not transaction_parse_result.is_valid():
                all_transactions_to_upload.append(tx)
                continue
            if transaction_parse_result.is_income:
                TransactionUpdater.update_income_transaction(tx, transaction_parse_result)
                # income transactions are not categorized yet
                all_transactions_as_income.append(tx)
                continue
            if transaction_parse_result.description:
                transaction_from_description = Transaction.objects.filter(
                    user=self.user,
                    normalized_description=normalize_string(transaction_parse_result.description),
                    transaction_date=transaction_parse_result.date,
                    category__isnull=False,
                    status='categorized'
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
                tx.embedding = generate_embedding(transaction_parse_result.description)
                reference_transaction, _ = self.find_rag_context(tx.embedding, self.user)
                if reference_transaction and is_rag_reliable(transaction_parse_result.description, reference_transaction.description,
                                               reference_transaction.merchant.name):
                    final_reference_transaction = self.similarity_matcher.find_most_frequent_transaction_for_merchant(reference_transaction.merchant)
                    categorized_transaction = TransactionUpdater.update_categorized_transaction(
                        tx,
                        transaction_parse_result,
                        final_reference_transaction
                    )
                    all_transactions_categorized.append(categorized_transaction)
                    merchant_with_category[categorized_transaction.merchant.name] = categorized_transaction.merchant, categorized_transaction.category
                else:
                    uncategorized_transaction = TransactionUpdater.update_transaction_with_parse_result(tx, transaction_parse_result)
                    all_transactions_to_upload.append(uncategorized_transaction)
            if tx.embedding is None:
                tx.embedding = generate_embedding(tx.description)

        Transaction.objects.bulk_update(all_transactions_categorized + all_transactions_to_upload + all_transactions_as_income,
                                        ['status', 'merchant', 'merchant_raw_name', 'category', 'transaction_date',
                                         'original_date', 'description', 'amount', 'original_amount',
                                         'transaction_type', 'normalized_description','operation_type', 'embedding'])
        Transaction.objects.filter(user=self.user, id__in=[tx.id for tx in all_transactions_to_delete]).delete()
        logger.info(
            f"Found {len(all_transactions_categorized)} {'👌' if len(all_transactions_categorized) > 0 else '😩'} transactions that have similar merchant names."
        )
        return all_transactions_to_upload

    def _process_with_agent(self, batch: list[Transaction], upload_file: UploadFile) -> tuple[list[TransactionCategorization], GeminiResponse | None]:
        agent_upload_transaction = []
        for tx in batch:
            # Assicuriamoci che l'embedding sia presente
            if tx.embedding is None:
                tx.embedding = generate_embedding(tx.description or "")

            _, useful_context = self.find_rag_context(tx.embedding, self.user)
            rag_context_data = [
                {
                    'description': ctx_tx.description,
                    'category': ctx_tx.category.name,
                    'merchant': ctx_tx.merchant.name
                }
                for ctx_tx in useful_context
            ]

            agent_upload_transaction.append(
                AgentTransactionUpload(
                    transaction_id=tx.id,
                    raw_text=tx.raw_data,
                    rag_context=rag_context_data
                )
            )

        if agent_upload_transaction:
            try:
                return self.agent.process_batch(agent_upload_transaction, upload_file)
            except Exception as e:
                logger.error(f"⚠️  Agent failed to process batch: {str(e)}")
                return [], None
            finally:
                connections.close_all()
        return [], None

    def _persist_batch_results(self, batch: list[TransactionCategorization]):
        transactions_to_update = []
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
                if not merchant_name or not category_name:
                    Transaction.objects.filter(id=tx_id).update(status='uncategorized', failure_code=1)
                    continue

                merchant, _ = Merchant.objects.get_or_create(name=merchant_name, user=self.user)
                category = Category.objects.filter(name__icontains=category_name.strip(), user=self.user).first()
                if not category:
                    Transaction.objects.filter(id=tx_id).update(status='uncategorized', failure_code=1, merchant=merchant)
                    continue

                transaction_from_agent = Transaction.objects.filter(user=self.user,
                                                                   id=tx_id).first() or Transaction.objects.filter(
                    user=self.user, description=description).first()

                if not transaction_from_agent:
                    continue

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
                if transaction_from_agent.embedding is None:
                    transaction_from_agent.embedding = generate_embedding(transaction_from_agent.description)
                transactions_to_update.append(transaction_from_agent)

            except Exception as e:
                logger.error(f"⚠️  Failed to persist transaction {tx_id}: {str(e)}")
                continue

        if transactions_to_update:
            Transaction.objects.bulk_update(transactions_to_update, [
                'category', 'merchant', 'merchant_raw_name', 'original_date', 'original_amount',
                'transaction_date', 'amount', 'status', 'modified_by_user', 'failure_code',
                'description', 'normalized_description', 'categorized_by_agent', 'reasoning', 'embedding'
            ])



    def _post_process_transactions(self, upload_file: UploadFile) -> None:
        """Post-process transactions after batch processing to identify column mappings and categorize uncategorized transactions."""
        self._categorize_remaining_transactions(upload_file)

    def _categorize_remaining_transactions(self, upload_file: UploadFile) -> None:
        """Process uncategorized transactions by parsing their data and attempting to categorize them using similar transactions."""
        uncategorized_transactions = Transaction.objects.filter(
            user=self.user,
            upload_file=upload_file,
            status__in=['uncategorized', 'pending']
        )

        for tx in uncategorized_transactions:
            parse_result = parse_raw_transaction(tx.raw_data, [upload_file])
            if not parse_result.is_valid():
                tx.status = 'uncategorized'
                continue

            TransactionUpdater.update_transaction_with_parse_result(tx, parse_result)
            tx.merchant_raw_name = parse_result.merchant

            # Only try to find similar transactions if we have a description
            if tx.description:
                similar_tx, _ = self.find_rag_context(generate_embedding(tx.description), self.user)
                if similar_tx and is_rag_reliable(tx.description, similar_tx.description, similar_tx.merchant.name):
                    similar_tx = self.similarity_matcher.find_most_frequent_transaction_for_merchant(similar_tx.merchant)
                    TransactionUpdater.update_categorized_transaction(tx, parse_result, similar_tx)
                    tx.embedding = similar_tx.embedding if any(similar_tx.embedding) else generate_embedding(tx.description)
                else:
                    tx.status = 'uncategorized'
            else:
                tx.status = 'uncategorized'

        uncategorized_transactions_list = list(uncategorized_transactions)

        Transaction.objects.bulk_update(
            uncategorized_transactions_list,
            ['transaction_date', 'amount', 'original_amount', 'description',
             'merchant_raw_name', 'original_date', 'category', 'status', 'merchant', 'normalized_description', 'embedding']
        )
        Transaction.objects.filter(user=self.user, upload_file=upload_file, status__in=['pending', 'uncategorized'],
                                   original_amount__isnull=True).update(status='uncategorized',
                                                                        transaction_type='income')

def persist_uploaded_file(file_data: list[dict[str, str]], user: User, file: UploadedFile) -> UploadFile:
    upload_file = UploadFile.objects.create(user=user, dimension=file.size, file_name=file.name)
    all_pending_transactions = [Transaction(
        upload_file=upload_file,
        user=user,
        status='pending',
        raw_data=file_row,
    ) for file_row in file_data]
    Transaction.objects.bulk_create(all_pending_transactions)
    return upload_file