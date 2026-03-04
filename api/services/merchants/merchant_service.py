from collections import Counter

from django.contrib.auth.models import User
from django.db.models import F

from api.models import Merchant
from api.privacy_utils import generate_blind_index, generate_encrypted_trigrams
from api.views.functions import ArrayIntersectionCount


class MerchantService:

    @staticmethod
    def get_merchants_candidates(search_term: str, user: User, max_results: int) -> list[Merchant]:
        hashed_user_input = generate_blind_index(search_term)
        merchants_from_db = Merchant.objects.filter(name_hash=hashed_user_input, user=user)
        exact_match = merchants_from_db.first()
        if exact_match:
            return [exact_match]
        hashed_user_input = generate_encrypted_trigrams(search_term)
        # Format trigrams for PostgreSQL array syntax: ['a', 'b'] -> "'a','b'"
        formatted_trigrams = ",".join([f"'{tg}'" for tg in hashed_user_input])
        merchants_from_db = (Merchant.objects
        .filter(fuzzy_search_trigrams__overlap=hashed_user_input,
                user=user)
        .annotate(
            match_score=ArrayIntersectionCount(
                F('fuzzy_search_trigrams'),
                search_trigrams=formatted_trigrams
            )
        )).order_by('-match_score')[:max_results]
        results = []
        for merchant in merchants_from_db:
            if merchant.name.lower().find(search_term.lower()) != -1:
                results.append(
                    (merchant, merchant.match_score)
                )
        best_results = sorted(results, key=lambda x: x[1], reverse=True)[:max_results]
        return [best_merchant for best_merchant, _ in best_results]
