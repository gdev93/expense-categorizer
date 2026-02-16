import datetime
import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.views import View
from asgiref.sync import sync_to_async
from api.models import Transaction
from exporters.exporters import generate_transaction_csv, generate_transaction_csv_async

from api.views.transactions.transaction_mixins import TransactionFilterMixin

class TransactionExportView(LoginRequiredMixin, TransactionFilterMixin, View):

    async def post(self, request, *args, **kwargs):
        # Update session filters if POST data is provided
        return await self._export(request)

    async def _export(self, request):
        # Ensure user is loaded in async context
        await request.auser()
        # get_transaction_filter_query might perform sync DB lookups for default filters
        queryset = await sync_to_async(self.get_transaction_filter_query)()
        
        # Optimize query: select_related for file metadata
        iterator = queryset.select_related('upload_file', 'category', 'merchant')

        # Exporter Layer: Use the async generator to stream the response
        response = StreamingHttpResponse(
            generate_transaction_csv_async(iterator),
            content_type='text/csv'
        )
        
        # File name for the download
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{self.request.user.username}_transactions_export_{timestamp}.csv"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
