import os
from collections import Counter

from django.db.models import F
from django.views.generic import ListView

from api.models import Merchant
from api.privacy_utils import encrypt_value, generate_blind_index, generate_encrypted_trigrams
from api.services import MerchantService


class MerchantSearchView(ListView):
    model = Merchant
    template_name = 'transactions/components/merchant_search_results.html'
    context_object_name = 'merchants'
    max_distinct_results = os.environ.get('MAX_MERCHANT_RESULTS', 5)

    def get_queryset(self):
        search_term = self.request.GET.get('name') or self.request.GET.get('merchant_name')
        if not search_term or len(search_term) < 2:
            return Merchant.objects.none()
        return MerchantService.get_merchants_candidates(search_term, self.request.user, self.max_distinct_results)
