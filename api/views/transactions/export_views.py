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
    """
    API view to export transactions as a memory-efficient CSV stream.
    """
    def get(self, request, *args, **kwargs):
        # We now support GET too, which will use session filters
        return self._export(request)

    def post(self, request, *args, **kwargs):
        # Update session filters if POST data is provided
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST
            
            # Update session with POST data to keep it consistent
            for key in ['year', 'search', 'amount', 'amount_operator', 'status', 'view_type']:
                if key in data:
                    request.session[f'filter_{key}'] = data[key]
            if 'months' in data:
                request.session['filter_months'] = data['months']
            if 'category' in data or 'categories' in data:
                request.session['filter_category'] = data.get('category') or data.get('categories')
            if 'upload_file' in data:
                request.session['filter_upload_file'] = data['upload_file']

        except (json.JSONDecodeError, AttributeError):
            pass

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
