import itertools
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction, connections
from django.db.models import Count, Max, Q

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
    pre_check_iterator_fetch_size = os.environ.get('PRE_CHECK_ITERATOR_FETCH_SIZE', 50)
    file_structure_sample_size_percentage = os.environ.get('CSV_STRUCTURE_SAMPLE_SIZE_PERCENTAGE', 0.1)
    file_structure_min_threshold = os.environ.get('CSV_STRUCTURE_MIN_THRESHOLD', 30)
    rag_identical_threshold = os.environ.get('RAG_IDENTICAL_THRESHOLD', 0.02) # 98% sure
    rag_reliable_threshold = os.environ.get('RAG_RELIABLE_THRESHOLD', 0.15) # very likely
    rag_context_threshold = os.environ.get('RAG_CONTEXT_THRESHOLD', 0.35) # context for gemini

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

    def process_transactions(self, transactions: Iterable[Transaction], upload_file: UploadFile) -> UploadFile:

        # Ensure we have an iterator
        transactions_iter = iter(transactions)

        # 1. Take a sample for structure detection
        sample = list(itertools.islice(transactions_iter, self.pre_check_iterator_fetch_size))
        if sample:
            self.file_structure_detector.setup_upload_file_structure(sample, upload_file)
            # Recombine sample with the rest
            transactions_iter = itertools.chain(sample, transactions_iter)

        logger.info(f"🚀 Starting CSV Processing for: {upload_file.file_name}")

        # 2. Process pre-checks and batch for agent using generators to save memory
        def get_transactions_to_upload():
            while True:
                chunk = list(itertools.islice(transactions_iter, self.pre_check_iterator_fetch_size))
                if not chunk:
                    break
                yield from self._process_prechecks(chunk, upload_file)

        def get_agent_batches():
            to_upload_iter = get_transactions_to_upload()
            while True:
                batch = list(itertools.islice(to_upload_iter, self.batch_helper.batch_size))
                if not batch:
                    break
                yield batch

        with ThreadPoolExecutor() as executor:
            # Parallelize the agent calls only
            # 1) Thread executor asks for agent batch
            # 2) agent batch asks for transaction to upload
            # 3) transaction to upload are fetched in batch from the database and preprocessed
            # Thread executor does not wait the first get_agent_batch to complete, but it keeps asking the get_agent_batch as soon as there is a free thread in the loop and there is an actual batch
            results = executor.map(lambda batch: self._process_with_agent(batch, upload_file), get_agent_batches())

            # Process each batch's results synchronously as they come
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

        # 1. Parsing & Collection
        parsed_data = []
        merchant_names_to_fetch = set()
        descriptions_to_embed = set()

        for tx in batch:
            res = parse_raw_transaction(tx.raw_data, [upload_file])
            parsed_data.append((tx, res))
            if res.is_valid():
                if res.merchant:
                    merchant_names_to_fetch.add(res.merchant)
                if res.description:
                    descriptions_to_embed.add(res.description.strip())

        # 2. Batch Level 1 & 2: Fetch Known Merchants
        # Fetching by name or normalized_name to handle exact and fuzzy-ish matches
        merchant_map = {}
        if merchant_names_to_fetch:
            normalized_names = [normalize_string(n) for n in merchant_names_to_fetch]
            merchants = Merchant.objects.filter(
                Q(name__in=merchant_names_to_fetch) | Q(normalized_name__in=normalized_names),
                user=self.user
            )
            for m in merchants:
                # We map both original and normalized for high-speed lookup
                merchant_map[m.name.lower()] = m
                merchant_map[m.normalized_name] = m

        # 3. Batch Level 3: Bulk Embed
        embedding_dict = {}
        if descriptions_to_embed:
            desc_list = list(descriptions_to_embed)
            embeddings_gen = EmbeddingEngine.get_model().embed(desc_list)
            for desc, emb in zip(desc_list, embeddings_gen):
                embedding_dict[desc] = emb.tolist()

        # 4. Processing Waterfall
        for tx, res in parsed_data:
            if not res.is_valid():
                all_transactions_to_upload.append(tx)
                continue

            if res.is_income:
                TransactionUpdater.update_income_transaction(tx, res)
                all_transactions_as_income.append(tx)
                continue

            # Check for duplicates
            if res.description:
                if Transaction.objects.filter(
                        user=self.user,
                        normalized_description=normalize_string(res.description),
                        transaction_date=res.date,
                        status='categorized'
                ).exists():
                    all_transactions_to_delete.append(tx)
                    continue

            # WATERFALL START
            categorized = False

            # Level A: Direct Merchant Match (from our batch map)
            m_lookup = res.merchant.lower() if res.merchant else None
            m_norm_lookup = normalize_string(res.merchant) if res.merchant else None
            merchant_obj = merchant_map.get(m_lookup) or merchant_map.get(m_norm_lookup)

            if merchant_obj:
                ref_tx = self.similarity_matcher.find_most_frequent_transaction_for_merchant(merchant_obj)
                if ref_tx:
                    TransactionUpdater.update_categorized_transaction(tx, res, ref_tx)
                    tx.embedding = embedding_dict.get(res.description.strip())
                    all_transactions_categorized.append(tx)
                    categorized = True

            # Level B: Vector RAG (if not found by merchant name)
            if not categorized and res.description:
                tx.embedding = embedding_dict.get(res.description.strip())
                if tx.embedding:
                    # find_rag_context is inherited from SimilarityMatcherRAG
                    ref_tx, useful_context = self.find_rag_context(tx.embedding, self.user)
                    tx.rag_context = useful_context

                    if ref_tx:
                        dist = getattr(ref_tx, 'distance', 1.0)
                        # Reliability logic
                        is_trusted = dist <= self.rag_identical_threshold
                        is_likely = dist <= self.rag_reliable_threshold and is_rag_reliable(
                            res.description, ref_tx.description, ref_tx.merchant.name
                        )

                        if is_trusted or is_likely:
                            final_ref = self.similarity_matcher.find_most_frequent_transaction_for_merchant(
                                ref_tx.merchant)
                            TransactionUpdater.update_categorized_transaction(tx, res, final_ref or ref_tx)
                            all_transactions_categorized.append(tx)
                            categorized = True

            # Level C: Fallback to Agent
            if not categorized:
                uncategorized_tx = TransactionUpdater.update_transaction_with_parse_result(tx, res)
                uncategorized_tx.embedding = embedding_dict.get(res.description.strip()) if res.description else None
                all_transactions_to_upload.append(uncategorized_tx)

        # 5. Bulk Persistence
        to_update = all_transactions_categorized + all_transactions_to_upload + all_transactions_as_income
        Transaction.objects.bulk_update(to_update, [
            'status', 'merchant', 'merchant_raw_name', 'category', 'transaction_date',
            'original_date', 'description', 'amount', 'original_amount',
            'transaction_type', 'normalized_description', 'operation_type', 'embedding'
        ])

        if all_transactions_to_delete:
            Transaction.objects.filter(id__in=[t.id for t in all_transactions_to_delete]).delete()

        logger.info(
            f"Batch processed: {len(all_transactions_categorized)} auto-categorized, {len(all_transactions_to_upload)} sent to agent.")
        return all_transactions_to_upload

    def _process_with_agent(self, batch: list[Transaction], upload_file: UploadFile) -> tuple[list[TransactionCategorization], GeminiResponse | None]:
        agent_upload_transaction = []
        for tx in batch:
            # Check if we already have the context from _process_prechecks
            useful_context = getattr(tx, 'rag_context', None)

            if useful_context is None:
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

        if any(agent_upload_transaction):
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

        iterator = uncategorized_transactions.iterator()
        while True:
            chunk = list(itertools.islice(iterator, self.pre_check_iterator_fetch_size))
            if not chunk:
                break

            for tx in chunk:
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

            Transaction.objects.bulk_update(
                chunk,
                ['transaction_date', 'amount', 'original_amount', 'description',
                 'merchant_raw_name', 'original_date', 'category', 'status', 'merchant', 'normalized_description', 'embedding']
            )

        Transaction.objects.filter(user=self.user, upload_file=upload_file, status__in=['pending', 'uncategorized'],
                                   original_amount__isnull=True).update(status='uncategorized',
                                                                        transaction_type='income')

def persist_uploaded_file(file_data: list[dict[str, str]], user: User, file: UploadedFile) -> UploadFile:
    upload_file = UploadFile.objects.create(user=user, dimension=file.size, file_name=file.name)

    # Use a generator expression to avoid creating all Transaction objects at once
    transactions_gen = (Transaction(
        upload_file=upload_file,
        user=user,
        status='pending',
        raw_data=file_row,
    ) for file_row in file_data)

    # Save in chunks of self.pre_check_iterator_fetch_size
    while True:
        chunk = list(itertools.islice(transactions_gen, ExpenseUploadProcessor.pre_check_iterator_fetch_size))
        if not chunk:
            break
        Transaction.objects.bulk_create(chunk)

    return upload_file