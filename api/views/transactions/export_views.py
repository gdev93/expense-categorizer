import datetime
import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.views import View
from api.models import Transaction
from exporters.exporters import generate_transaction_csv

class TransactionExportView(LoginRequiredMixin, View):
    """
    API view to export transactions as a memory-efficient CSV stream.
    """
    def post(self, request, *args, **kwargs):
        # Extract parameters from POST body
        try:
            # Handle both JSON and form data
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST
        except (json.JSONDecodeError, AttributeError):
            data = {}

        # 1. Selector Layer: Filter transactions for the authenticated user
        queryset = Transaction.objects.filter(user=request.user)

        # 2. Apply filters from Design Document
        upload_ids = data.get('upload_ids', [])
        if upload_ids:
            if isinstance(upload_ids, str):
                try:
                    upload_ids = json.loads(upload_ids)
                except json.JSONDecodeError:
                    upload_ids = [upload_ids]
            queryset = queryset.filter(csv_upload_id__in=upload_ids)
        
        start_date = data.get('start_date')
        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
            
        end_date = data.get('end_date')
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)

        # 3. Apply additional filters from current UI (to match TransactionListView)
        transaction_type = data.get('transaction_type')
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)

        category_id = data.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        year = data.get('year')
        if year:
            queryset = queryset.filter(transaction_date__year=year)

        months = data.get('months')
        if months:
            if isinstance(months, str):
                months = [months]
            month_queries = Q()
            for m in months:
                try:
                    month_queries |= Q(transaction_date__month=int(m))
                except (ValueError, TypeError):
                    pass
            if month_queries:
                queryset = queryset.filter(month_queries)

        search_query = data.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(merchant_raw_name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        amount = data.get('amount')
        amount_operator = data.get('amount_operator', 'eq')
        if amount:
            try:
                amount_value = float(amount)
                if amount_operator == 'eq':
                    queryset = queryset.filter(amount=amount_value)
                elif amount_operator == 'gt':
                    queryset = queryset.filter(amount__gt=amount_value)
                elif amount_operator == 'gte':
                    queryset = queryset.filter(amount__gte=amount_value)
                elif amount_operator == 'lt':
                    queryset = queryset.filter(amount__lt=amount_value)
                elif amount_operator == 'lte':
                    queryset = queryset.filter(amount__lte=amount_value)
            except (ValueError, TypeError):
                pass
        only_expense = data.get('only_expense', True)
        if only_expense:
            queryset = queryset.filter(transaction_type='expense')
        # Optimize query: select_related for file metadata and .iterator() for memory efficiency
        iterator = queryset.select_related('csv_upload').order_by('-transaction_date', '-created_at').iterator()

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
