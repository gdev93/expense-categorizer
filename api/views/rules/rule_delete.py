from django.urls import reverse_lazy
from django.views.generic import DeleteView
from api.models import Rule

class RuleDeleteView(DeleteView):
    model = Rule
    success_url = reverse_lazy('transaction_list')

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)
