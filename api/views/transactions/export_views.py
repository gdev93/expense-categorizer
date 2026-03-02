import csv
import datetime
import io

from asgiref.sync import sync_to_async
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import StreamingHttpResponse
from django.views import View

from api.views.transactions.transaction_mixins import TransactionFilterMixin

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


async def generate_csv(transactions_iterator):
    """
    An async generator that yields CSV rows for the given transactions iterator.

    Args:
        transactions_iterator: An async iterable of Transaction model instances.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    headers = ['Data', 'Importo', 'Categoria', 'Descrizione Bancaria', 'Tipo di Transazione', 'File Sorgente']
    writer.writerow(headers)
    yield output.getvalue()
    output.truncate(0)
    output.seek(0)

    async for tx in transactions_iterator:
        row = get_transaction_csv_row(tx)
        writer.writerow(row)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)


def generate_csv_sync(transactions_iterator):
    """
    A sync generator that yields CSV rows for the given transactions iterator.

    Args:
        transactions_iterator: An iterable of Transaction model instances.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    headers = ['Data', 'Importo', 'Categoria', 'Descrizione Bancaria', 'Tipo di Transazione', 'File Sorgente']
    writer.writerow(headers)
    yield output.getvalue()
    output.truncate(0)
    output.seek(0)

    for tx in transactions_iterator:
        row = get_transaction_csv_row(tx)
        writer.writerow(row)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)


def get_transaction_csv_row(tx):
    """
    Returns a list of values for a CSV row for a given Transaction instance.
    """
    return [
        tx.transaction_date.isoformat() if tx.transaction_date else '',
        tx.amount,
        tx.category.name if tx.category else '',
        tx.description,
        tx.transaction_type,
        tx.upload_file.file_name if tx.upload_file else 'Inserimento manuale'
    ]