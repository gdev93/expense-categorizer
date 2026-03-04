from django.db import transaction
from django.db.models import Min
from django.urls import reverse_lazy
from django.views.generic import DeleteView

from api.models import UploadFile, Transaction
from api.services.data_refresh.data_refresh_service import DataRefreshService

class UploadFileDelete(DeleteView):
    model = UploadFile
    template_name = 'transactions/upload_file_confirm_delete.html'
    success_url = reverse_lazy('transactions_upload')

    def get_queryset(self):
        return self.model.objects.filter(user=self.request.user)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        upload_file = self.get_object()
        # Efficiently get the earliest transaction date before deletion
        # result will be something like {'transaction_date__min': datetime.date(2025, 11, 15)}
        aggregation = Transaction.objects.filter(upload_file=upload_file).aggregate(Min('transaction_date'))
        start_date = aggregation['transaction_date__min']

        Transaction.objects.filter(upload_file=upload_file).delete()
        
        response = super().post(request, *args, **kwargs)

        # Recompute after deletion: remove only those that are NOT linked to other manual transactions
        Transaction.objects.filter(
            user=request.user,
            manual_insert=False,
            upload_file__isnull=True
        ).delete()

        if start_date:
            DataRefreshService.trigger_recomputation(request.user, start_date)

        return response
