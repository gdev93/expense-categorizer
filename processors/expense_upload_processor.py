import itertools
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q
from django.db.models.expressions import RawSQL

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, TransactionCategorization, GeminiResponse
from api.models import Transaction, Category, Merchant, UploadFile, normalize_string
from api.privacy_utils import generate_blind_index
from costs.services import CostService
from processors.batching_helper import BatchingHelper
from processors.data_prechecks import parse_raw_transaction
from processors.embeddings import EmbeddingEngine
from processors.parser_utils import normalize_amount, parse_raw_date
from processors.similarity_matcher import (
    SimilarityMatcher, generate_embedding, SimilarityMatcherRAG,
    update_merchant_ema
)
from processors.transaction_updater import TransactionUpdater
from processors.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class ExpenseUploadProcessor(SimilarityMatcherRAG):
    """
    Handles the processing and persistence of uploaded expense transactions.

    Responsibilities:
    - Batch processing through agent
    - Persistence of results
    - Progress tracking and logging
    """
    pre_check_confidence_threshold = float(os.environ.get('PRE_CHECK_CONFIDENCE_THRESHOLD', '0.85'))
    pre_check_iterator_fetch_size = int(os.environ.get('PRE_CHECK_ITERATOR_FETCH_SIZE', '50'))
    gemini_max_retries = int(os.environ.get('GEMINI_MAX_RETRIES', '5'))
    gemini_base_delay = int(os.environ.get('GEMINI_BASE_DELAY', '2'))

    def __init__(self, user: User, user_rules: list[str] = None, available_categories: list[Category] | None = None, batch_helper:BatchingHelper | None = None):
        self.user = user
        self.batch_helper = batch_helper or BatchingHelper()
        self.agent = ExpenseCategorizerAgent(user_rules=user_rules, available_categories=available_categories)
        self.similarity_matcher = SimilarityMatcher(user)

    def process_transactions(self, transactions: Iterable[Transaction], upload_file: UploadFile) -> UploadFile:

        # Ensure we have an iterator
        transactions_iter = iter(transactions)

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
                # It keeps asking for slices untile it stops at batch_helper_size
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
                        self._persist_batch_results(batch_result, upload_file)

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
        merchant_with_category = dict()

        for tx in batch:
            res = parse_raw_transaction(tx.raw_data, [upload_file])
            parsed_data.append((tx, res))
            if res.is_valid():
                if res.merchant:
                    merchant_names_to_fetch.add(res.merchant)
                if res.description:
                    descriptions_to_embed.add(res.description.strip())

        # 2. Batch Level 1 & 2: Fetch Known Merchants
        # Fetching by name_hash to handle exact matches
        merchant_map = {}
        if merchant_names_to_fetch:
            merchant_hashes = [generate_blind_index(n) for n in merchant_names_to_fetch]
            merchants = Merchant.objects.filter(
                name_hash__in=merchant_hashes,
                user=self.user
            )
            for m in merchants:
                # We map by name_hash for high-speed lookup
                merchant_map[m.name_hash] = m

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
                        description_hash=generate_blind_index(res.description),
                        transaction_date=res.date,
                        status='categorized'
                ).exists():
                    all_transactions_to_delete.append(tx)
                    continue

            # WATERFALL START
            categorized = False

            # Level A: Direct Merchant Match (from our batch map)
            m_hash = generate_blind_index(res.merchant) if res.merchant else None
            merchant_obj = merchant_map.get(m_hash)

            if merchant_obj:
                ref_tx = merchant_with_category.get(merchant_obj) or self.similarity_matcher.find_most_frequent_transaction_for_merchant(merchant_obj)
                if ref_tx:
                    merchant_with_category[merchant_obj] = ref_tx
                    TransactionUpdater.update_categorized_transaction(tx, res, ref_tx)
                    tx.embedding = embedding_dict.get(res.description.strip())
                    if tx.embedding:
                        update_merchant_ema(merchant_obj, upload_file.file_structure_metadata, tx.embedding)
                    all_transactions_categorized.append(tx)
                    categorized = True

            # Level B: Vector RAG (if not found by merchant name)
            if not categorized and res.description:
                tx.embedding = embedding_dict.get(res.description.strip())
                if tx.embedding:
                    # find_rag_context is inherited from SimilarityMatcherRAG
                    useful_context = self.find_rag_context(tx.embedding, self.user)
                    tx.rag_context = useful_context
                    final_ref = None
                    earliest_index = float('inf')
                    for ctx_ema in useful_context:
                        merchant_name = ctx_ema.merchant.name.lower()
                        description_to_check = res.description.lower()
                        pos = description_to_check.find(merchant_name)
                        # Merchant candidates have precedence if they show in the first part of the description
                        if pos != -1 and pos < earliest_index:
                            earliest_index = pos
                            final_ref = ctx_ema
                    if final_ref:
                        final_ref_most_frequent = merchant_with_category.get(final_ref.merchant)
                        if not final_ref_most_frequent:
                            final_ref_most_frequent = self.similarity_matcher.find_most_frequent_transaction_for_merchant(final_ref.merchant)
                            if final_ref_most_frequent:
                                merchant_with_category[final_ref.merchant] = final_ref_most_frequent

                        if final_ref_most_frequent:
                            TransactionUpdater.update_categorized_transaction(tx, res, final_ref_most_frequent)
                            update_merchant_ema(final_ref.merchant, upload_file.file_structure_metadata, tx.embedding)
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
            'status', 'merchant', 'category', 'transaction_date',
            'encrypted_description', 'amount', 'description_hash',
            'transaction_type', 'operation_type', 'embedding'
        ])

        if all_transactions_to_delete:
            Transaction.objects.filter(id__in=[t.id for t in all_transactions_to_delete]).delete()

        logger.info(
            f"Batch processed: {len(all_transactions_categorized)} auto-categorized, {len(all_transactions_to_upload)} sent to agent.")
        return all_transactions_to_upload

    def _process_with_agent(self, batch: list[Transaction], upload_file: UploadFile) -> tuple[
        list[TransactionCategorization], GeminiResponse | None]:
        agent_upload_transaction = []

        # 1. Collect all unique merchants across the entire batch to avoid repeated queries
        merchant_map = {}
        for tx in batch:
            useful_context = getattr(tx, 'rag_context', []) or []
            for ema in useful_context:
                # Store the merchant object to avoid re-fetching it later
                # and use its ID as the key to ensure uniqueness in the map.
                merchant_map[ema.merchant_id] = ema.merchant

        # 2. Pre-fetch the most frequent transaction for each unique merchant
        # We store these in a dictionary to reuse them for different transactions in the same batch
        merchant_to_frequent_tx = {
            m_id: self.similarity_matcher.find_most_frequent_transaction_for_merchant(m_obj)
            for m_id, m_obj in merchant_map.items()
        }

        for tx in batch:
            # Check if we already have the context from _process_prechecks
            useful_context = getattr(tx, 'rag_context', []) or []
            rag_context_data = []
            for ctx_ema in useful_context:
                frequent_tx = merchant_to_frequent_tx.get(ctx_ema.merchant_id)
                if frequent_tx:
                    rag_context_data.append({
                        'description': frequent_tx.description,
                        'category': frequent_tx.category.name,
                        'merchant': frequent_tx.merchant.name
                    })

            agent_upload_transaction.append(
                AgentTransactionUpload(
                    transaction_id=tx.id,
                    raw_text=tx.raw_data,
                    rag_context=rag_context_data
                )
            )

        if any(agent_upload_transaction):
            return retry_with_backoff(
                self.agent.process_batch,
                max_retries=self.gemini_max_retries,
                base_delay=self.gemini_base_delay,
                on_failure=([], None),
                batch=agent_upload_transaction,
                upload_file=upload_file
            )

        return [], None

    def _persist_batch_results(self, batch: list[TransactionCategorization], upload_file: UploadFile):
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
                    Transaction.objects.filter(id=tx_id).update(status='uncategorized')
                    continue

                merchant_hash = generate_blind_index(merchant_name)
                merchant = Merchant.objects.filter(name_hash=merchant_hash, user=self.user).first()
                if not merchant:
                    merchant = Merchant.objects.create(name=merchant_name, user=self.user)
                category = Category.objects.filter(name__icontains=category_name.strip(), user=self.user).first()
                if not category:
                    Transaction.objects.filter(id=tx_id).update(status='uncategorized', merchant=merchant)
                    continue

                transaction_from_agent = Transaction.objects.filter(user=self.user,
                                                                   id=tx_id).first() or Transaction.objects.filter(
                    user=self.user, description_hash=generate_blind_index(description)).first()

                if not transaction_from_agent:
                    continue

                transaction_from_agent.category = category
                transaction_from_agent.merchant = merchant
                transaction_from_agent.transaction_date = transaction_date if not transaction_from_agent.transaction_date else transaction_from_agent.transaction_date
                transaction_from_agent.amount = abs(
                    amount) if not transaction_from_agent.amount else transaction_from_agent.amount
                transaction_from_agent.status = 'categorized'
                transaction_from_agent.modified_by_user = False
                transaction_from_agent.description = tx_data.description if not transaction_from_agent.description else transaction_from_agent.description
                transaction_from_agent.categorized_by_agent = True
                transaction_from_agent.reasoning = tx_data.reasoning
                if transaction_from_agent.embedding is None:
                    transaction_from_agent.embedding = generate_embedding(transaction_from_agent.description)
                
                # Update Merchant EMA
                update_merchant_ema(merchant, upload_file.file_structure_metadata, transaction_from_agent.embedding)
                
                transactions_to_update.append(transaction_from_agent)

            except Exception as e:
                logger.error(f"⚠️  Failed to persist transaction {tx_id}: {str(e)}")
                continue

        if transactions_to_update:
            Transaction.objects.bulk_update(transactions_to_update, [
                'category', 'merchant',
                'transaction_date', 'amount', 'status', 'modified_by_user',
                'encrypted_description', 'description_hash', 'categorized_by_agent', 'embedding'
            ])



    def _post_process_transactions(self, upload_file: UploadFile) -> None:
        """Post-process transactions after batch processing to identify column mappings and categorize uncategorized transactions."""
        self._categorize_remaining_transactions(upload_file)
        self._clean_transactions_raw_data(upload_file)

    
    def _clean_transactions_raw_data(self, upload_file:UploadFile):
        """Clean the raw data of transactions for privacy reasons."""
        Transaction.objects.filter(upload_file=upload_file).update(raw_data=None, embedding=None)
        logger.info(f"Raw data of {upload_file.file_name} has been cleaned.")

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

                # Only try to find similar transactions if we have a description
                if tx.description:
                    if tx.embedding is None:
                        tx.embedding = generate_embedding(tx.description)

                    if any(tx.embedding):
                        # find_rag_context is inherited from SimilarityMatcherRAG
                        useful_context = self.find_rag_context(tx.embedding, self.user)
                        tx.rag_context = useful_context
                        final_ref = None
                        earliest_index = float('inf')
                        for ctx_tx in useful_context:
                            merchant_name = ctx_tx.merchant.name.lower()
                            description_to_check = parse_result.description.lower()
                            pos = description_to_check.find(merchant_name)
                            # Merchant candidates have precedence if they show in the first part of the description
                            if pos != -1 and pos < earliest_index:
                                earliest_index = pos
                                final_ref = ctx_tx

                        if final_ref:
                            ref_tx = self.similarity_matcher.find_most_frequent_transaction_for_merchant(final_ref.merchant)
                            if ref_tx:
                                TransactionUpdater.update_categorized_transaction(tx, parse_result, ref_tx)
                                # Update EMA since we found a reliable match
                                update_merchant_ema(final_ref.merchant, upload_file.file_structure_metadata, tx.embedding)
                            else:
                                tx.status = 'uncategorized'
                        else:
                            tx.status = 'uncategorized'
                    else:
                        tx.status = 'uncategorized'
                else:
                    tx.status = 'uncategorized'

            Transaction.objects.bulk_update(
                chunk,
                ['transaction_date', 'amount', 'encrypted_description', 'description_hash',
                 'category', 'status', 'merchant', 'embedding']
            )

        Transaction.objects.filter(user=self.user, upload_file=upload_file, status__in=['pending', 'uncategorized'],
                                   amount__isnull=True).update(status='uncategorized',
                                                                        transaction_type='income')

def persist_uploaded_file(file_data: list[dict[str, str]], user: User, file: UploadedFile, upload_file: UploadFile = None) -> UploadFile:
    if upload_file is None:
        upload_file = UploadFile.objects.create(user=user, dimension=file.size, file_name=file.name)
    else:
        upload_file.dimension = file.size
        upload_file.file_name = file.name
        upload_file.save()

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