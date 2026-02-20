from decimal import Decimal
from typing import Iterable, Dict, Optional, Tuple, Any
from django.db.models import QuerySet
from api.privacy_utils import decrypt_value

class TransactionAggregationService:
    """Service to handle aggregations of transactions with encrypted amounts."""

    @staticmethod
    def calculate_total_amount(queryset_or_iterable: Any) -> Decimal:
        """Calculate the total amount of transactions by decrypting each amount."""
        total_amount = Decimal('0')
        
        if isinstance(queryset_or_iterable, QuerySet):
            # Optimization: Fetch only encrypted_amount
            items = queryset_or_iterable.values('encrypted_amount')
        elif isinstance(queryset_or_iterable, list) and queryset_or_iterable and hasattr(queryset_or_iterable[0], 'encrypted_amount'):
            items = [{'encrypted_amount': tx.encrypted_amount} for tx in queryset_or_iterable]
        else:
            items = queryset_or_iterable

        for item in items:
            val = decrypt_value(item.get('encrypted_amount'))
            if val:
                try:
                    total_amount += Decimal(val)
                except (ValueError, TypeError):
                    pass
        return total_amount

    @staticmethod
    def calculate_merchant_sums(queryset: QuerySet, merchant_ids: Iterable[int]) -> Dict[int, Decimal]:
        """Calculate the sum of transactions for each merchant in merchant_ids."""
        sums = {m_id: Decimal('0') for m_id in merchant_ids}
        
        tx_data = queryset.filter(merchant_id__in=merchant_ids).values('merchant_id', 'encrypted_amount')
        for tx in tx_data:
            m_id = tx['merchant_id']
            val = decrypt_value(tx['encrypted_amount'])
            if val:
                try:
                    sums[m_id] += Decimal(val)
                except (ValueError, TypeError):
                    pass
        return sums

    @staticmethod
    def calculate_category_sums(queryset: QuerySet, category_ids: Iterable[int]) -> Dict[int, Decimal]:
        """Calculate the sum of transactions for each category in category_ids."""
        sums = {c_id: Decimal('0') for c_id in category_ids}
        
        tx_data = queryset.filter(category_id__in=category_ids).values('category_id', 'encrypted_amount')
        for tx in tx_data:
            c_id = tx['category_id']
            val = decrypt_value(tx['encrypted_amount'])
            if val:
                try:
                    sums[c_id] += Decimal(val)
                except (ValueError, TypeError):
                    pass
        return sums

    @staticmethod
    def calculate_category_monthly_sums(queryset: QuerySet) -> Dict[Tuple[str, int], Decimal]:
        """Calculate the sum of transactions grouped by category name and month."""
        from collections import defaultdict
        grouped_data = defaultdict(Decimal)
        
        tx_data = queryset.select_related('category').values(
            'category__name', 'encrypted_amount', 'transaction_date__month'
        )
        
        for tx in tx_data:
            cat_name = tx['category__name']
            month = tx['transaction_date__month']
            if not cat_name or not month:
                continue
            
            val = decrypt_value(tx['encrypted_amount'])
            if val:
                try:
                    grouped_data[(cat_name, month)] += Decimal(val)
                except (ValueError, TypeError):
                    pass
        return grouped_data
