import datetime
from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse
from django.views import View
from .transaction_mixins import TransactionFilterMixin
from .utils import generate_csv

class TransactionExportView(TransactionFilterMixin, View):

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
            generate_csv(iterator),
            content_type='text/csv'
        )
        
        # File name for the download
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{self.request.user.username}_transactions_export_{timestamp}.csv"

        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
