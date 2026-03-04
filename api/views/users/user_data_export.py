from datetime import datetime
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.views import View
from api.models import Transaction
from api.views.transactions.utils import generate_csv_sync


class UserDataExportView(View):
    """View to export all user data in CSV format"""

    def get(self, request: HttpRequest) -> HttpResponse:
        user = request.user

        # Collect transactions for all time
        queryset = Transaction.objects.filter(user=user).select_related("category", "upload_file", "merchant").order_by("-transaction_date")

        # Exporter Layer: Use the sync generator to stream the response
        response = StreamingHttpResponse(
            generate_csv_sync(queryset.iterator()),
            content_type='text/csv'
        )

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"pecuniam_export_{user.username}_{timestamp}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        return response
