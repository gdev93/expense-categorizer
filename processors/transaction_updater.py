from api.models import Transaction, Category, Merchant, normalize_string
from processors.data_prechecks import RawTransactionParseResult

class TransactionUpdater:
    @staticmethod
    def _update_common_fields(tx: Transaction, parse_result: RawTransactionParseResult) -> Transaction:
        tx.amount = abs(parse_result.amount)
        tx.original_amount = parse_result.original_amount
        tx.transaction_date = parse_result.date
        tx.original_date = parse_result.date_original
        tx.description = parse_result.description
        tx.normalized_description = normalize_string(parse_result.description)
        tx.operation_type = parse_result.operation_type
        return tx

    @staticmethod
    def update_transaction_with_parse_result(tx: Transaction,
                                            transaction_parse_result: RawTransactionParseResult) -> Transaction:
        """
        Update basic transaction fields from parse result.
        """
        return TransactionUpdater._update_common_fields(tx, transaction_parse_result)

    @staticmethod
    def update_income_transaction(tx: Transaction, parse_result: RawTransactionParseResult) -> Transaction:
        """
        Update income transaction fields.
        """
        tx.transaction_type = 'income'
        tx.status = 'categorized'
        return TransactionUpdater._update_common_fields(tx, parse_result)

    @staticmethod
    def update_categorized_transaction_with_category_merchant(tx: Transaction, category: Category, merchant: Merchant,
                                                               transaction_parse_result: RawTransactionParseResult) -> Transaction:
        tx.status = 'categorized'
        tx.merchant = merchant
        tx.category = category
        return TransactionUpdater._update_common_fields(tx, transaction_parse_result)

    @staticmethod
    def update_categorized_transaction(
            tx: Transaction,
            transaction_parse_result: RawTransactionParseResult,
            reference_transaction: Transaction
    ) -> Transaction:
        """
        Create a categorized transaction based on a reference transaction.
        """
        tx.status = 'categorized'
        tx.merchant = reference_transaction.merchant
        tx.category = reference_transaction.category
        return TransactionUpdater._update_common_fields(tx, transaction_parse_result)
