import logging
import os

from django.contrib.auth.models import User
from django.db.models import Count, Max
from django.contrib.postgres.search import TrigramWordSimilarity
from api.models import Transaction, Merchant, normalize_string
from processors.data_prechecks import RawTransactionParseResult

logger = logging.getLogger(__name__)

class SimilarityMatcher:
    def __init__(self, user: User, threshold: float):
        self.user = user
        self.threshold = threshold
        self.fuzzy_match_depth = os.getenv('FUZZY_MATCH_DEPTH', 5)

    def find_similar_transaction_by_merchant(self, merchant_name: str) -> Transaction | None:
        """
        Finds the best matching categorized transaction based on a merchant name candidate.
        """
        # 1. Try Strict/Normalized Match on the Merchant Relation first (High Confidence)
        normalized_candidate = normalize_string(merchant_name)

        exact_matches = Transaction.objects.filter(
            user=self.user,
            category__isnull=False,
            transaction_type='expense',
            merchant__normalized_name=normalized_candidate
        )

        best_category_exact = exact_matches.values('category').annotate(
            count=Count('category'),
            latest_date=Max('transaction_date')
        ).order_by('-count', '-latest_date').first()

        if best_category_exact:
            return exact_matches.filter(category_id=best_category_exact['category']).order_by('-transaction_date').first()

        # 2. Try Fuzzy Match on 'merchant_raw_name' (Medium Confidence)
        fuzzy_matches = Transaction.objects.annotate(
            similarity=TrigramWordSimilarity(merchant_name, 'merchant_raw_name')
        ).filter(
            user=self.user,
            category__isnull=False,
            transaction_type='expense',
            similarity__gte=self.threshold
        )

        best_category_fuzzy = fuzzy_matches.values('category').annotate(
            count=Count('category'),
            max_similarity=Max('similarity'),
            latest_date=Max('transaction_date')
        ).order_by('-count', '-max_similarity', '-latest_date').first()

        if best_category_fuzzy:
            return fuzzy_matches.filter(category_id=best_category_fuzzy['category']).order_by('-similarity', '-transaction_date').first()

        return None

    def find_reference_transaction_from_tx(self, tx: Transaction) -> Transaction | None:
        """Find reference transaction from an existing Transaction object."""
        if tx.merchant:
            return self.find_similar_transaction_by_merchant(tx.merchant.name)
        return None

    def find_reference_transaction_from_raw(self,
                                            transaction_parse_result: RawTransactionParseResult) -> Transaction | None:
        if transaction_parse_result.merchant:
            similar_transaction = self.find_similar_transaction_by_merchant(transaction_parse_result.merchant)
            if similar_transaction:
                return similar_transaction

        desc = transaction_parse_result.description
        if desc:
            # Get all merchants that meet the threshold
            merchants_from_description = Merchant.get_merchants_by_transaction_description(
                desc, self.user, self.threshold
            )

            if merchants_from_description.exists():
                # Strategy: Find the merchant whose name appears EARLIEST in the description.
                # This prioritizes the "Creditor" over the "Debtor" in SDD strings.
                best_merchant = None
                earliest_index = float('inf')

                for merchant in merchants_from_description[:self.fuzzy_match_depth]:  # Check top fuzzy candidates
                    # Find the position of the merchant name in the raw description
                    pos = desc.lower().find(merchant.name.lower())

                    if pos != -1 and pos < earliest_index:
                        earliest_index = pos
                        best_merchant = merchant

                if best_merchant:
                    return self.find_similar_transaction_by_merchant(best_merchant.name)

        return None