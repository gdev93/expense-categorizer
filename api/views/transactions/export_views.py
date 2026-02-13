import datetime
import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.views import View
from api.models import Transaction
from exporters.exporters import generate_transaction_csv

from api.views.transactions.transaction_mixins import TransactionFilterMixin

class TransactionExportView(LoginRequiredMixin, TransactionFilterMixin, View):

    def post(self, request, *args, **kwargs):
        # Update session filters if POST data is provided
        return self._export(request)

    def _export(self, request):
        queryset = self.get_transaction_filter_query()
        
        # Optimize query: select_related for file metadata and .iterator() for memory efficiency
        iterator = queryset.select_related('upload_file', 'category', 'merchant').iterator()

        # Exporter Layer: Use the generator to stream the response
        response = StreamingHttpResponse(
            generate_transaction_csv(iterator),
            content_type='text/csv'
        )
        
        # File name for the download
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{self.request.user.username}_transactions_export_{timestamp}.csv"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
