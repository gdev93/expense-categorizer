from django.views.generic import ListView

from api.models import Merchant


class MerchantSearchView(ListView):
    model = Merchant

    def get_queryset(self):
        search_term = self.request.GET.get('name')
        return super().get_queryset().filter(user=self.request.user,name__icontains=search_term)
