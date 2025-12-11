import os
from math import floor

from django.contrib.auth.models import User
from django.contrib.postgres.search import TrigramWordSimilarity
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, TransactionCategorization
from api.models import Transaction, Category, Merchant, CsvUpload, normalize_string
from processors.data_prechecks import parse_raw_transaction, RawTransactionParseResult
from processors.parser_utils import normalize_amount, parse_raw_date, parse_amount_from_raw_data_without_suggestion, \
    parse_date_from_raw_data_with_no_suggestions


class BatchingHelper:
    batch_size = os.environ.get('AGENT_BATCH_SIZE', 15)
    batch_max_size = os.environ.get('AGENT_BATCH_MAX_SIZE', 20)
    batch_min_size = os.environ.get('AGENT_BATCH_MIN_SIZE', 12)
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


def _update_transaction_with_parse_result(tx: Transaction,
                                          transaction_parse_result: RawTransactionParseResult) -> Transaction:
    """
    Create an uncategorized transaction.
    """
    tx.amount = abs(transaction_parse_result.amount)
    tx.original_amount = transaction_parse_result.original_amount
    tx.transaction_date = transaction_parse_result.date
    tx.original_date = transaction_parse_result.date_original
    tx.description = transaction_parse_result.description
    tx.normalized_description = normalize_string(transaction_parse_result.description)
    return tx


def _update_categorized_transaction_with_category_merchant(tx: Transaction, category: Category, merchant: Merchant,
                                                           transaction_parse_result: RawTransactionParseResult) -> Transaction:
    tx.status = 'categorized'
    tx.merchant = merchant
    tx.merchant_raw_name = merchant.normalized_name
    tx.category = category
    tx.transaction_date = transaction_parse_result.date
    tx.original_date = transaction_parse_result.date_original
    tx.description = transaction_parse_result.description
    tx.normalized_description = normalize_string(transaction_parse_result.description)
    tx.amount = abs(transaction_parse_result.amount)
    tx.original_amount = transaction_parse_result.original_amount
    return tx

def _update_categorized_transaction(
        tx: Transaction,
        transaction_parse_result: RawTransactionParseResult,
        reference_transaction: Transaction
) -> Transaction:
    """
    Create a categorized transaction based on a reference transaction.
    """
    tx.status = 'categorized'
    tx.merchant = reference_transaction.merchant
    tx.merchant_raw_name = reference_transaction.merchant.normalized_name
    tx.category = reference_transaction.category
    tx.transaction_date = transaction_parse_result.date
    tx.original_date = transaction_parse_result.date_original
    tx.description = transaction_parse_result.description
    tx.normalized_description = normalize_string(transaction_parse_result.description)
    tx.amount = abs(transaction_parse_result.amount)
    tx.original_amount = transaction_parse_result.original_amount
    return tx


def _find_similar_transaction_by_merchant(
        user: User,
        merchant_name: str,
        threshold: float
) -> Transaction | None:
    """
    Finds the best matching categorized transaction based on a merchant name candidate.
    """
    # 1. Try Strict/Normalized Match on the Merchant Relation first (High Confidence)
    #    If we have a Transaction linked to a Merchant whose name matches our candidate.
    normalized_candidate = normalize_string(merchant_name)

    exact_match_tx = Transaction.objects.filter(
        user=user,
        category__isnull=False,
        transaction_type='expense',
        merchant__normalized_name=normalized_candidate
    ).order_by('-transaction_date').first()

    if exact_match_tx:
        return exact_match_tx

    # 2. Try Fuzzy Match on 'merchant_raw_name' (Medium Confidence)
    #    Useful if the merchant wasn't linked to a Merchant object but the raw name is similar.
    #    We use TrigramWordSimilarity on the RAW name (preserving spaces) for better word matching.
    fuzzy_match_tx = Transaction.objects.annotate(
        similarity=TrigramWordSimilarity(merchant_name, 'merchant_raw_name')
    ).filter(
        user=user,
        category__isnull=False,
        transaction_type='expense',
        similarity__gte=threshold
    ).order_by('-similarity', '-transaction_date').first()

    return fuzzy_match_tx


def _find_similar_transaction_by_description(
        user: User,
        description: str,
        precheck_confidence_threshold: float,
) -> Transaction | None:
    """Search for a similar categorized transaction by description similarity."""

    return Transaction.objects.annotate(
        description_similarity=TrigramWordSimilarity(description, 'description')
    ).filter(
        status='categorized',
        merchant_id__isnull=False,
        user=user,
        description_similarity__gte=precheck_confidence_threshold
    ).order_by('-description_similarity', '-updated_at').first()


def _find_reference_transaction_from_tx(
        user: User,
        tx: Transaction,
        precheck_confidence_threshold: float
) -> Transaction | None:
    """Find reference transaction from an existing Transaction object."""
    # Check if tx has a merchant and search for similar transactions by merchant
    if tx.merchant:
        similar_transaction = _find_similar_transaction_by_merchant(user, tx.merchant.name,
                                                                    precheck_confidence_threshold)
        if similar_transaction:
            return similar_transaction

    # Fall back to description similarity search
    return _find_similar_transaction_by_description(
        user,
        tx.description,
        precheck_confidence_threshold
    )

# TODO Per gli addebiti, se c'è il nome del debitore, ma un merchant ha lo stesso nome (esempio giroconto verso un conto intensato all'utente) passa la query ilike
def _find_reference_transaction_from_raw(
        user: User,
        transaction_parse_result: RawTransactionParseResult,
        precheck_confidence_threshold: float
) -> Transaction | None:
    """Find reference transaction from a raw transaction parse result."""
    # Check if parse result has a merchant and search for similar transactions
    if transaction_parse_result.merchant:
        similar_transaction = _find_similar_transaction_by_merchant(
            user,
            transaction_parse_result.merchant,
            precheck_confidence_threshold
        )
        if similar_transaction:
            return similar_transaction
    if transaction_parse_result.description:
        merchants_from_description = Merchant.get_merchants_by_transaction_description(
            transaction_parse_result.description, user, precheck_confidence_threshold
        )
        if merchants_from_description.count() == 1:
            return _find_similar_transaction_by_merchant(user, merchants_from_description[0].name,
                                                         precheck_confidence_threshold)
    # Fall back to description similarity search
    return _find_similar_transaction_by_description(
        user,
        transaction_parse_result.description,
        precheck_confidence_threshold
    )

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
            if transaction_parse_result.amount > 0:
                print(f"Only expenses are allowed, skipping transaction {transaction_parse_result.raw_data}")
                tx.transaction_type = 'income'
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
                    print(f"Transaction from description {transaction_parse_result.description} already categorized")
                    all_transactions_to_delete.append(tx)
                    continue
            if transaction_parse_result.merchant and merchant_with_category.get(transaction_parse_result.merchant):
                merchant, category = merchant_with_category[transaction_parse_result.merchant]
                categorized_transaction = _update_categorized_transaction_with_category_merchant(tx, category, merchant,
                                                                                                 transaction_parse_result)
                all_transactions_categorized.append(categorized_transaction)
            else:
                reference_transaction = _find_reference_transaction_from_raw(self.user,
                                                                             transaction_parse_result,
                                                                             self.pre_check_confidence_threshold)
                if reference_transaction:
                    categorized_transaction = _update_categorized_transaction(
                        tx,
                        transaction_parse_result,
                        reference_transaction
                    )
                    all_transactions_categorized.append(categorized_transaction)
                    merchant_with_category[categorized_transaction.merchant.name] = categorized_transaction.merchant, categorized_transaction.category
                else:
                    uncategorized_transaction = _update_transaction_with_parse_result(tx, transaction_parse_result)
                    all_transactions_to_upload.append(uncategorized_transaction)

        Transaction.objects.bulk_update(all_transactions_categorized + all_transactions_to_upload,
                                        ['status', 'merchant', 'merchant_raw_name', 'category', 'transaction_date',
                                         'original_date', 'description', 'amount', 'original_amount',
                                         'transaction_type', 'normalized_description'])
        Transaction.objects.filter(user=self.user, id__in=[tx.id for tx in all_transactions_to_delete]).delete()
        print(
            f"Found {len(all_transactions_categorized)} {"👌" if len(all_transactions_categorized) > 0 else "😩"} transactions that have similar merchant names"
        )
        return all_transactions_to_upload

    def _process_batch(self, batch: list[Transaction], csv_upload: CsvUpload):
        agent_upload_transaction = [AgentTransactionUpload(transaction_id=tx.id, raw_text=tx.raw_data) for tx in
                                    batch]
        if agent_upload_transaction:
            batch_result = self.agent.process_batch(agent_upload_transaction, csv_upload)
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

                similar_transaction = _find_similar_transaction_by_merchant(user=self.user, merchant_name=merchant_name,
                                                                            threshold=self.pre_check_confidence_threshold)
                if not similar_transaction:
                    merchant = Merchant(name=merchant_name, user=self.user)
                    merchant.save()
                    category = Category.objects.filter(name__icontains=category_name.strip(), user=self.user).first()
                    if not category:
                        print(
                            f"Agent response {tx_data} did not use the list of categories given by the user. Set transaction uncategorized.")
                        Transaction.objects.filter(id=tx_id).update(status='uncategorized', failure_code=1)
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
                transaction_from_agent.save()

            except Exception as e:
                print(f"⚠️  Failed to persist transaction {tx_id}: {str(e)}")
                continue
    def _setup_csv_upload_structure(self, current_data:list[Transaction], csv_upload: CsvUpload):
        csv_upload_same_structure = None
        all_csv_uploads = list(CsvUpload.objects.filter(user=self.user).exclude(id=csv_upload.id))
        for csv_upload_candidate in all_csv_uploads:
            first_transaction_candidate = Transaction.objects.filter(user=self.user, csv_upload=csv_upload_candidate,
                                                                     original_amount__isnull=False,
                                                                     category__isnull=False).first()
            if not first_transaction_candidate:
                continue
            first_transaction_raw_data = first_transaction_candidate.raw_data
            first_transaction_raw_data_keys = set(first_transaction_raw_data.keys())
            new_transaction_raw_data_keys = set(current_data[0].raw_data.keys())
            # the idea is to check that each element in the set in the other set
            if first_transaction_raw_data_keys == new_transaction_raw_data_keys:
                csv_upload_same_structure = csv_upload_candidate
                break
        if not csv_upload_same_structure:
            transaction_sample_size = min(len(current_data), max(self.csv_structure_min_threshold, floor(len(current_data) * self.csv_structure_sample_size_percentage)))  # 30%
            result_from_agent = self.agent.detect_csv_structure(
                [AgentTransactionUpload(transaction_id=tx.id, raw_text=tx.raw_data) for tx in
                 current_data[:transaction_sample_size]])
            description_column_name = result_from_agent.description_field
            notes = result_from_agent.notes
            merchant_column_name = result_from_agent.merchant_field
            date_column_name = result_from_agent.transaction_date_field
            amount_column_name = result_from_agent.amount_field
            operation_type_column_name = result_from_agent.operation_type_field
        else:
            description_column_name = csv_upload_same_structure.description_column_name
            notes = csv_upload_same_structure.notes
            merchant_column_name = csv_upload_same_structure.merchant_column_name
            date_column_name = csv_upload_same_structure.date_column_name
            amount_column_name = csv_upload_same_structure.amount_column_name
            operation_type_column_name = csv_upload_same_structure.operation_type_column_name

        csv_upload.description_column_name = description_column_name
        csv_upload.merchant_column_name = merchant_column_name
        csv_upload.date_column_name = date_column_name
        csv_upload.amount_column_name = amount_column_name
        csv_upload.operation_type_column_name = operation_type_column_name
        csv_upload.notes = notes
        csv_upload.save()

    def process_transactions(self, transactions: list[Transaction], csv_upload: CsvUpload) -> CsvUpload:

        self._setup_csv_upload_structure(transactions, csv_upload)

        all_transactions_to_upload = self._process_prechecks(transactions, csv_upload)
        data_count = len(all_transactions_to_upload)
        batch_size = self.batch_helper.compute_batch_size(data_count)
        total_batches = (data_count + batch_size - 1) // batch_size

        print(f"\n{'=' * 60}")
        print(f"🚀 Starting CSV Processing: {data_count} transactions")
        print(f"{'=' * 60}\n")
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = start_idx + batch_size
            batch = all_transactions_to_upload[start_idx:end_idx]
            with transaction.atomic():
                self._process_batch(batch, csv_upload)

        with transaction.atomic():
            self._post_process_transactions(csv_upload)

        return csv_upload

    def _post_process_transactions(self, csv_upload: CsvUpload) -> None:
        """Post-process transactions after batch processing to identify column mappings and categorize uncategorized transactions."""
        self._categorize_remaining_transactions(csv_upload)
        self._apply_transaction_type_corrections(csv_upload)
        #TODO sanity check for rules

    def _identify_csv_column_mappings(self, csv_upload: CsvUpload) -> None:
        """Identify and tag CSV column names by matching against completed categorized transactions."""

        # Track which columns we still need to find
        columns_to_find = {
            'amount_column_name': csv_upload.amount_column_name is None,
            'date_column_name': csv_upload.date_column_name is None,
            'description_column_name': csv_upload.description_column_name is None,
            'merchant_column_name': csv_upload.merchant_column_name is None
        }

        # If all columns are already identified, skip
        if not any(columns_to_find.values()):
            return

        # Fetch transactions one at a time until all columns are identified
        completed_transactions = Transaction.objects.filter(
            user=self.user,
            csv_upload=csv_upload,
            status='categorized',
            original_amount__isnull=False,
            description__isnull=False,
            transaction_type='expense',
            original_date__isnull=False
        ).iterator(chunk_size=10)

        for tx in completed_transactions:
            # Check if we've found all columns
            if not any(columns_to_find.values()):
                break

            # Try to match each column we haven't found yet
            for key, value in tx.raw_data.items():
                # Check amount column
                if columns_to_find['amount_column_name'] and value == tx.original_amount:
                    csv_upload.amount_column_name = key
                    columns_to_find['amount_column_name'] = False

                # Check date column
                elif columns_to_find['date_column_name'] and value == tx.original_date:
                    csv_upload.date_column_name = key
                    columns_to_find['date_column_name'] = False

                # Check description column
                elif columns_to_find['description_column_name'] and value == tx.description:
                    csv_upload.description_column_name = key
                    columns_to_find['description_column_name'] = False

                # Check merchant column
                elif columns_to_find['merchant_column_name'] and value == tx.merchant_raw_name:
                    csv_upload.merchant_column_name = key
                    columns_to_find['merchant_column_name'] = False

        # Save if any columns were identified
        if csv_upload.amount_column_name or csv_upload.date_column_name or \
                csv_upload.description_column_name or csv_upload.merchant_column_name:
            csv_upload.save()

    def _categorize_remaining_transactions(self, csv_upload: CsvUpload) -> None:
        """Process uncategorized transactions by parsing their data and attempting to categorize them using similar transactions."""
        uncategorized_transactions = Transaction.objects.filter(
            user=self.user,
            csv_upload=csv_upload,
            status__in=['uncategorized', 'pending'],
            # The AI detects the correct columns, so income type of transaction have no amount
            original_amount__isnull=False
        )

        for tx in uncategorized_transactions:
            # Get values from raw_data, handling None column names
            original_amount = tx.raw_data.get(csv_upload.amount_column_name,
                                              '') if csv_upload.amount_column_name else ''
            description = tx.raw_data.get(csv_upload.description_column_name,
                                          '') if csv_upload.description_column_name else ''
            merchant = tx.raw_data.get(csv_upload.merchant_column_name, '') if csv_upload.merchant_column_name else ''
            original_date = tx.raw_data.get(csv_upload.date_column_name, '') if csv_upload.date_column_name else ''

            if not original_amount:
                parsed_amount_result = parse_amount_from_raw_data_without_suggestion(tx.raw_data)
                if parsed_amount_result.is_valid():
                    for column_name, amount_finding in parsed_amount_result.fields.items():
                        if column_name in tx.raw_data:
                            original_amount = tx.raw_data[column_name]
                            if original_amount != amount_finding.original_value:
                                continue

                            break

            # If description is still empty, try to infer it from raw_data
            if not description:
                # Look for a description-like field in raw_data
                for key, value in tx.raw_data.items():
                    if value and isinstance(value, str) and len(
                            value) > 20:  # Heuristic: descriptions are usually longer
                        description = value
                        break

            if not original_date:
                try:
                    date, _ = parse_date_from_raw_data_with_no_suggestions(tx.raw_data)
                    if date:
                        tx.transaction_date = date
                        tx.original_date = original_date
                except Exception:
                    print(f"Failed to parse date from transaction {tx.id} with raw data: {tx.raw_data}")

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
                similar_tx = _find_reference_transaction_from_tx(csv_upload.user, tx,
                                                                 self.pre_check_confidence_threshold)
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

    def _apply_transaction_type_corrections(self, csv_upload: CsvUpload) -> None:
        """Correct transaction types for transactions marked as expense but are actually income (positive amounts)."""
        # Find all transactions that are categorized and marked as expense but actually they are income transaction
        (Transaction.objects.filter(
            user=self.user,
            csv_upload=csv_upload
        )
         .filter(Q(original_amount__isnull=True) & Q(category__isnull=False))
         .update(transaction_type='income', status='uncategorized'))


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