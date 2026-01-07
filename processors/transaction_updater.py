from api.models import Transaction, Category, Merchant, normalize_string
from processors.data_prechecks import RawTransactionParseResult

class TransactionUpdater:
    @staticmethod
    def update_transaction_with_parse_result(tx: Transaction,
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

    @staticmethod
    def update_categorized_transaction_with_category_merchant(tx: Transaction, category: Category, merchant: Merchant,
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
        tx.merchant_raw_name = reference_transaction.merchant.normalized_name
        tx.category = reference_transaction.category
        tx.transaction_date = transaction_parse_result.date
        tx.original_date = transaction_parse_result.date_original
        tx.description = transaction_parse_result.description
        tx.normalized_description = normalize_string(transaction_parse_result.description)
        tx.amount = abs(transaction_parse_result.amount)
        tx.original_amount = transaction_parse_result.original_amount
        return tx
