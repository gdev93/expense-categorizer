import logging
from django.contrib.auth.models import User
from django.contrib.postgres.search import TrigramWordSimilarity
from api.models import Transaction, Merchant, normalize_string
from processors.data_prechecks import RawTransactionParseResult

logger = logging.getLogger(__name__)

class SimilarityMatcher:
    def __init__(self, user: User, threshold: float):
        self.user = user
        self.threshold = threshold

    def find_similar_transaction_by_merchant(self, merchant_name: str) -> Transaction | None:
        """
        Finds the best matching categorized transaction based on a merchant name candidate.
        """
        # 1. Try Strict/Normalized Match on the Merchant Relation first (High Confidence)
        normalized_candidate = normalize_string(merchant_name)

        exact_match_tx = Transaction.objects.filter(
            user=self.user,
            category__isnull=False,
            transaction_type='expense',
            merchant__normalized_name=normalized_candidate
        ).order_by('-transaction_date').first()

        if exact_match_tx:
            return exact_match_tx

        # 2. Try Fuzzy Match on 'merchant_raw_name' (Medium Confidence)
        fuzzy_match_tx = Transaction.objects.annotate(
            similarity=TrigramWordSimilarity(merchant_name, 'merchant_raw_name')
        ).filter(
            user=self.user,
            category__isnull=False,
            transaction_type='expense',
            similarity__gte=self.threshold
        ).order_by('-similarity', '-transaction_date').first()

        return fuzzy_match_tx

    def find_reference_transaction_from_tx(self, tx: Transaction) -> Transaction | None:
        """Find reference transaction from an existing Transaction object."""
        if tx.merchant:
            return self.find_similar_transaction_by_merchant(tx.merchant.name)
        return None

    # TODO Per gli addebiti, se c'è il nome del debitore, ma un merchant ha lo stesso nome (esempio giroconto verso un conto intensato all'utente) passa la query ilike
    def find_reference_transaction_from_raw(self, transaction_parse_result: RawTransactionParseResult) -> Transaction | None:
        """Find reference transaction from a raw transaction parse result."""
        if transaction_parse_result.merchant:
            similar_transaction = self.find_similar_transaction_by_merchant(transaction_parse_result.merchant)
            if similar_transaction:
                return similar_transaction
        
        if transaction_parse_result.description:
            merchants_from_description = Merchant.get_merchants_by_transaction_description(
                transaction_parse_result.description, self.user, self.threshold
            )
            if merchants_from_description.count() == 1:
                return self.find_similar_transaction_by_merchant(merchants_from_description[0].name)
        
        return None
