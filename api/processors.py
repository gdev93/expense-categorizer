# processors.py
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Count

from agent.agent import ExpenseCategorizerAgent
from .models import Transaction, Category, Merchant


def _parse_date(tx_data: dict) -> date:
    """
    Parse transaction date from CSV data.

    Tries common date field names and formats.
    Returns a date object (not datetime).
    """
    # Common date field names
    date_fields = ['Data', 'Date', 'Transaction Date', 'data', 'date']

    for field in date_fields:
        if field in tx_data and tx_data[field]:
            date_str = tx_data[field]

            # Try common date formats
            for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue

    # Default to today if parsing fails
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

    def __init__(self, user, batch_size: int = 15, user_rules: list[str] = None,
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
        """
        Process all transactions in batches.

        Args:
            transactions: List of transactions with IDs and raw CSV data

        Returns:
            dictionary with processing results and statistics
        """
        results = []
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

                # Process batch through agent
                batch_result = self.agent.process_batch(batch, batch_num + 1)

                # Persist results immediately after batch processing
                if batch_result.get('success'):
                    persisted_count = self._persist_batch_results(batch, batch_result)
                    batch_result['persisted_count'] = persisted_count
                    print(f"💾 Batch {batch_num + 1} persisted: {persisted_count} transactions saved")
                else:
                    batch_result['persisted_count'] = 0
                    print(f"⚠️  Batch {batch_num + 1} not persisted due to processing error")

                results.append(batch_result)

        # Calculate final statistics
        stats = _calculate_statistics(transactions, results)

        print(f"\n{'=' * 60}")
        print(f"✅ Processing Complete!")
        print(f"   Total transactions: {stats['total']}")
        print(f"   Successful batches: {stats['successful_batches']}/{stats['total_batches']}")
        print(f"   Expenses categorized: {stats['total_categorized']}")
        print(f"   Transactions persisted: {stats['total_persisted']}")
        print(f"{'=' * 60}\n")

        return {
            'results': results,
            'statistics': stats
        }

    def _persist_batch_results(self, batch: list[dict], batch_result: dict) -> int:
        """
        Persist batch results to database.

        Args:
            batch: Original batch data with raw CSV rows
            batch_result: Agent processing results

        Returns:
            Number of transactions successfully persisted
        """
        all_results = batch_result.get('all_results', {})
        persisted_count = 0
        existing_transactions = (Transaction.objects
                                 .values('amount', 'merchant_raw_name', 'transaction_date')  # Group by these fields
                                 .annotate(count=Count('id'))  # Count the number of transactions in each group
                                 .filter(count__gte=1)  # Keep only the groups (combinations) with a count > 1
                                 .values_list('amount', 'merchant_raw_name','transaction_date', flat=False)
                                 )
        for tx_data in batch:
            tx_id = tx_data.get('id')
            result = all_results.get(tx_id)
            if not result:
                continue

            try:
                # Extract and parse transaction data
                transaction_date = _parse_date(tx_data)
                amount = _parse_amount(result.get('amount', 0))
                original_amount = result.get('original_amount', '')
                description = result.get('description', '')
                merchant_name = result.get('merchant', '')
                category_name = result.get('category', '')

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

                # Get or create merchant
                merchant = None
                if merchant_name:
                    merchant, _ = Merchant.objects.get_or_create(
                        name=merchant_name
                    )

                # Create transaction
                Transaction.objects.create(
                    user=self.user,
                    transaction_date=transaction_date,
                    amount=amount,
                    original_amount=original_amount,
                    description=description,
                    merchant=merchant,
                    merchant_raw_name=merchant_name,
                    category=category,
                    status='categorized',
                    confidence_score=None,
                    modified_by_user=False
                )

                persisted_count += 1

            except Exception as e:
                print(f"⚠️  Failed to persist transaction {tx_id}: {str(e)}")
                continue

        return persisted_count
