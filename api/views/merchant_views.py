import os

from django.views.generic import ListView

from api.models import Merchant
from api.privacy_utils import encrypt_value, generate_blind_index, generate_encrypted_trigrams


class MerchantSearchView(ListView):
    model = Merchant
    template_name = 'transactions/components/merchant_search_results.html'
    context_object_name = 'merchants'
    max_distinct_results = os.environ.get('MAX_MERCHANT_RESULTS', 5)

    def get_queryset(self):
        search_term = self.request.GET.get('name') or self.request.GET.get('merchant_name')
        if not search_term or len(search_term) < 2:
            return Merchant.objects.none()
        hashed_user_input = generate_blind_index(search_term)
        merchants_from_db = Merchant.objects.filter(name_hash=hashed_user_input, user=self.request.user)
        exact_match = merchants_from_db.first()
        if exact_match:
            return exact_match
        hashed_user_input = generate_encrypted_trigrams(search_term)
        merchants_from_db = Merchant.objects.filter(fuzzy_search_trigrams__overlap=hashed_user_input, user=self.request.user)
        return merchants_from_db.distinct('name').order_by('name')[:self.max_distinct_results]
