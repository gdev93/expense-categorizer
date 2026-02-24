from decimal import Decimal
from typing import Iterable, Dict, Tuple

from django.db.models import QuerySet

from api.models import Transaction


class TransactionAggregationService:
    """Service to handle aggregations of transactions with encrypted amounts."""

    @staticmethod
    def calculate_total_amount(queryset_or_iterable: list[Transaction] | QuerySet[Transaction, Transaction]) -> Decimal:
        """Calculate the total amount of transactions by using its amount property."""
        total_amount = Decimal('0')

        for item in queryset_or_iterable:
            val = item.amount
            if val:
                total_amount += val
        return total_amount

    @staticmethod
    def calculate_merchant_sums(queryset: QuerySet[Transaction, Transaction], merchant_ids: Iterable[int]) -> Dict[
        int, Decimal]:
        """Calculate the sum of transactions for each merchant in merchant_ids."""
        sums = {m_id: Decimal('0') for m_id in merchant_ids}

        tx_data = queryset.filter(merchant_id__in=merchant_ids)
        for tx in tx_data:
            m_id = tx.merchant_id
            val = tx.amount
            if val:
                sums[m_id] += val
        return sums

    @staticmethod
    def calculate_category_sums(queryset: QuerySet[Transaction, Transaction], category_ids: Iterable[int]) -> Dict[
        int, Decimal]:
        """Calculate the sum of transactions for each category in category_ids."""
        sums = {c_id: Decimal('0') for c_id in category_ids}

        tx_data = queryset.filter(category_id__in=category_ids)
        for tx in tx_data:
            c_id = tx.category_id
            val = tx.amount
            if val:
                sums[c_id] += val
        return sums

    @staticmethod
    def calculate_category_monthly_sums(queryset: QuerySet[Transaction, Transaction]) -> Dict[Tuple[str, int], Decimal]:
        """Calculate the sum of transactions grouped by category name and month."""
        from collections import defaultdict
        grouped_data = defaultdict(Decimal)

        tx_data = queryset.select_related('category')
        
        for tx in tx_data:
            cat_name = tx.category.name if tx.category else None
            month = tx.transaction_date.month if tx.transaction_date else None
            if not cat_name or not month:
                continue

            val = tx.amount
            if val:
                grouped_data[(cat_name, month)] += val
        return grouped_data
