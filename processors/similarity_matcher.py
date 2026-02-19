import logging
import os

from django.contrib.auth.models import User
from django.db.models import Count, Max

from api.models import Transaction, Merchant, normalize_string, FileStructureMetadata, MerchantEMA
from api.privacy_utils import generate_blind_index
from processors.embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)


def update_merchant_ema(merchant: Merchant, file_structure_metadata: FileStructureMetadata, embedding: list[float]):
    """
    Updates the Exponential Moving Average (EMA) of the merchant's digital footprint.
    Uses 0.9 as the old weight and 0.1 for the new weight.
    """
    if not any(embedding) or not merchant or not file_structure_metadata:
        return

    import numpy as np
    ema_obj, created = MerchantEMA.objects.get_or_create(
        merchant=merchant,
        file_structure_metadata=file_structure_metadata,
        defaults={'digital_footprint': embedding}
    )

    if not created:
        old_ema = np.array(ema_obj.digital_footprint)
        new_vec = np.array(embedding)
        # EMA Formula: 0.9 * old + 0.1 * new
        updated_ema = 0.9 * old_ema + 0.1 * new_vec
        ema_obj.digital_footprint = updated_ema.tolist()
        ema_obj.save()


def generate_embedding(description: str) -> list[float]:
    """
    Generates embedding for a transaction.
    """

    # Prepare text by combining Merchant (if detected) and Description
    texts = [(description or '').strip()]

    # embed returns a generator of numpy arrays
    embeddings = list(EmbeddingEngine.get_model().embed(texts))
    return embeddings[0].tolist() if embeddings else []


class SimilarityMatcherRAG:
    """
    Mixin per ExpenseUploadProcessor che implementa la logica RAG
    utilizzando FastEmbed e pgvector.
    """

    rag_context_threshold = os.getenv('RAG_CONTEXT_THRESHOLD', 0.45)

    def find_rag_context(self, embedding: list[float] | None, user:User) -> list[
        MerchantEMA]:
        if not any(embedding):
            return []
        from pgvector.django import CosineDistance

        merchant_emas = MerchantEMA.objects.filter(merchant__user=user).select_related('merchant').annotate(
            distance=CosineDistance('digital_footprint', embedding)
        ).filter(
            distance__lte=self.rag_context_threshold
        ).order_by('distance')


        # Recuperiamo le top 5 per il contesto
        context_results = list(merchant_emas[:5])

        if not context_results:
            return []

        return context_results
class SimilarityMatcher:
    def __init__(self, user: User):
        self.user = user

    def find_most_frequent_transaction_for_merchant(self, merchant: Merchant) -> Transaction | None:
        """
        Finds the most frequent categorized transaction for a given merchant (matching by normalized name).
        """
        best_category_candidate = (
            Transaction.objects.filter(user=self.user, merchant=merchant,
                                       status='categorized').values('category')
            .annotate(
                count=Count('category'), latest_date=Max('transaction_date')
            ).order_by('-count', '-latest_date').first()
        )
        if best_category_candidate:
            return Transaction.objects.filter(
                user=self.user,
                category__id=best_category_candidate['category'],
                merchant=merchant
            ).select_related('category', 'merchant').first()
        return None