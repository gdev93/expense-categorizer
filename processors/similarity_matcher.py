import logging
import os

import numpy as np
from django.contrib.auth.models import User
from django.contrib.postgres.search import TrigramWordSimilarity
from django.db.models import Count, Max
from django.db.models.expressions import RawSQL
from numpy import ndarray

from api.models import Transaction, Merchant, normalize_string
from processors.data_prechecks import RawTransactionParseResult
from processors.embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)


def generate_embedding(description: str) -> list[float]:
    """
    Generates embedding for a transaction.
    """

    # Prepare text by combining Merchant (if detected) and Description
    texts = [(description or '').strip()]

    # embed returns a generator of numpy arrays
    embeddings = list(EmbeddingEngine.get_model().embed(texts))
    return embeddings[0].tolist() if embeddings else []


def is_rag_reliable(new_desc:str, match_desc:str, target_merchant_name:str):
    """
    Verifica se il match RAG è affidabile confrontando le parole
    senza usare stop-words predefinite.
    """
    # 1. Estraiamo tutte le parole (solo lettere/numeri > 2 caratteri)
    import re
    def get_clean_words(text):
        return set(re.findall(r'\b\w{3,}\b', text.lower()))

    words_new = get_clean_words(new_desc)
    words_match = get_clean_words(match_desc)

    # 2. Troviamo le parole diverse (Symmetric Difference)
    # Queste sono le parole che "rompono" la somiglianza perfetta
    differences = words_new.symmetric_difference(words_match)

    # Se tra le differenze ci sono parole puramente testuali (non date/numeri)
    # come "PAROS" e "PITTAROSSO", dobbiamo insospettirci.

    important_diffs = [w for w in differences if not w.isdigit()]

    # 3. Se la distanza del RAG è > 0.01 (non è identico)
    # E ci sono parole diverse significative (nomi di negozi diversi)
    # allora blocchiamo l'auto-categorizzazione.
    if len(important_diffs) > 0:
        return new_desc.lower().find(target_merchant_name.lower()) != -1

    return True


class SimilarityMatcherRAG:
    """
    Mixin per ExpenseUploadProcessor che implementa la logica RAG
    utilizzando FastEmbed e pgvector.
    """


    AUTO_CATEGORIZE_THRESHOLD = os.getenv('AUTO_CATEGORIZE_THRESHOLD', 0.06)
    RAG_CONTEXT_THRESHOLD = os.getenv('RAG_CONTEXT_THRESHOLD', 0.25)

    def find_rag_context(self, embedding: list[float] | None, user: User):
        """
        Cerca nel database le transazioni passate più simili dell'utente.
        Ritorna una tupla: (best_match_transaction, list_of_context_transactions)
        """
        if not embedding:
            return None, []
        from pgvector.django import CosineDistance

        # Query pgvector: CosineDistance (più bassa è, più sono simili)
        # Filtriamo per transazioni già categorizzate o revisionate dello stesso utente
        similar_query = Transaction.objects.filter(
            user=user,
            status__in=['categorized'],
            transaction_type='expense',
            embedding__isnull=False
        ).annotate(
            distance=CosineDistance('embedding', embedding)
        ).order_by('distance')

        # Recuperiamo le top 5 per il contesto
        context_results = list(similar_query[:5])

        if not context_results:
            return None, []

        best_match = context_results[0]

        # Se la distanza è bassissima, possiamo considerarlo un match certo
        is_auto_match = best_match.distance <= self.AUTO_CATEGORIZE_THRESHOLD

        # Filtriamo per il contesto Gemini (solo quelle entro il threshold di utilità)
        useful_context = [
            tx for tx in context_results
            if tx.distance <= self.RAG_CONTEXT_THRESHOLD
        ]

        return (best_match if is_auto_match else None), useful_context
class SimilarityMatcher:
    def __init__(self, user: User, threshold: float):
        self.user = user
        self.threshold = threshold
        self.fuzzy_match_depth = os.getenv('FUZZY_MATCH_DEPTH', 5)

    def find_most_frequent_transaction_for_merchant(self, merchant: Merchant) -> Transaction | None:
        """
        Finds the most frequent categorized transaction for a given merchant (matching by normalized name).
        """
        best_category_candidate = (
            Transaction.objects.filter(user=self.user, merchant__normalized_name=merchant.normalized_name,
                                       status='categorized').values('category')
            .annotate(
                count=Count('category'), latest_date=Max('transaction_date')
            ).order_by('-count', '-latest_date').first()
        )
        if best_category_candidate:
            return Transaction.objects.filter(
                user=self.user,
                category__id=best_category_candidate['category'],
                merchant__normalized_name=merchant.normalized_name
            ).first()
        return None

    def find_similar_transaction_by_merchant(self, merchant_name: str) -> Transaction | None:
        """
        Finds the best matching categorized transaction based on a merchant name candidate.
        """
        # 1. Try Strict/Normalized Match on the Merchant Relation first (High Confidence)
        normalized_candidate = normalize_string(merchant_name)

        exact_matches = Merchant.objects.filter(
            user=self.user,
            normalized_name=normalized_candidate
        )

        if exact_matches.exists():
            return self.find_most_frequent_transaction_for_merchant(exact_matches.first())

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