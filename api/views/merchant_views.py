import os

from django.views.generic import ListView

from api.models import Merchant


class MerchantSearchView(ListView):
    model = Merchant
    template_name = 'transactions/components/merchant_search_results.html'
    context_object_name = 'merchants'
    max_distinct_results = os.environ.get('MAX_MERCHANT_RESULTS', 5)

    def get_queryset(self):
        search_term = self.request.GET.get('name') or self.request.GET.get('merchant_name')
        if not search_term or len(search_term) < 2:
            return Merchant.objects.none()
        return super().get_queryset().filter(
            user=self.request.user,
            name__icontains=search_term
        ).distinct('name').order_by('name')[:self.max_distinct_results]
