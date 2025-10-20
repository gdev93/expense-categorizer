# processors.py
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Count

from agent.agent import ExpenseCategorizerAgent, AgentTransactionUpload, TransactionCategorization
from .models import Transaction, Category, Merchant


def _parse_date(date_str: str) -> date:

    # Try common date formats
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y']:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return datetime.now().date()


def _parse_amount(amount_value) -> Decimal:
    """
    Parse amount to Decimal, handling various formats.
    """
    if isinstance(amount_value, (int, float)):
        return Decimal(str(abs(amount_value)))

    if isinstance(amount_value, str):
        try:
            # Remove currency symbols and spaces
            cleaned = amount_value.replace('€', '').replace(' ', '').strip()
            # Handle Italian format (comma as decimal separator)
            cleaned = cleaned.replace('.', '').replace(',', '.')
            return Decimal(abs(float(cleaned)))
        except (ValueError, InvalidOperation):
            return Decimal('0.00')

    return Decimal('0.00')


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

    def process_transactions(self, transactions: list[dict[str, str]]) -> dict:

        total_batches = (len(transactions) + self.batch_size - 1) // self.batch_size

        print(f"\n{'=' * 60}")
        print(f"🚀 Starting CSV Processing: {len(transactions)} transactions")
        print(f"{'=' * 60}\n")

        # Process each batch
        with transaction.atomic():
            for batch_num in range(total_batches):
                start_idx = batch_num * self.batch_size
                end_idx = start_idx + self.batch_size
                batch = transactions[start_idx:end_idx]
                all_pending_transactions = [Transaction(user=self.user,raw_data=tx) for tx in batch]
                Transaction.objects.bulk_create(all_pending_transactions)
                agent_upload_transaction = [AgentTransactionUpload(transaction_id=tx.id, raw_text=tx.raw_data) for tx in all_pending_transactions]
                # Process batch through agent
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
                failure_code = tx_data.failure_code
                # Extract and parse transaction data
                transaction_date = _parse_date(tx_data.date)
                amount = _parse_amount(tx_data.amount)
                original_amount = tx_data.original_amount
                description = tx_data.description
                merchant_name = tx_data.merchant
                category_name = tx_data.category

                # Skip if not an expense
                if category_name == 'not_expense':
                    continue
                if (amount, merchant_name, transaction_date) in existing_transactions:
                    continue
                # Get or create category
                category = None
                if category_name:
                    category, _ = Category.objects.get_or_create(
                        name=category_name,
                        user=self.user,
                        defaults={'is_default': False}
                    )
                else:
                    Category.objects.create(name='altro', user=self.user, defaults={'is_default': False})

                # Get or create merchant
                merchant = None
                if merchant_name:
                    merchant, _ = Merchant.objects.get_or_create(
                        name=merchant_name
                    )
                # Create transaction
                updated_count = Transaction.objects.filter(id=tx_id, user=self.user).update(
                    transaction_date=transaction_date,
                    amount=amount,
                    original_amount=original_amount,
                    description=description,
                    merchant=merchant,
                    merchant_raw_name=merchant_name,
                    category=category,
                    status='categorized' if not failure_code else 'uncategorized',
                    confidence_score=None,
                    modified_by_user=False,
                    failure_code=failure_code
                )

                if updated_count == 0:
                    print(f"⚠️ Transaction {tx_id} not found or doesn't belong to user")


            except Exception as e:
                print(f"⚠️  Failed to persist transaction {tx_id}: {str(e)}")
                continue