from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import ApiUsageLog, CostConfiguration
from .services import CostService
from django.db.models import Sum

class CostSummaryView(LoginRequiredMixin, ListView):
    model = ApiUsageLog
    template_name = 'costs/summary.html'
    context_object_name = 'logs'

    def get_queryset(self):
        try:
            get_year = self.request.GET.get('year')
            if get_year:
                selected_year = int(get_year)
            else:
                from api.models import Transaction
                import datetime
                last_t = Transaction.objects.filter(user=self.request.user, status='categorized').order_by('-transaction_date').first()
                selected_year = last_t.transaction_date.year if last_t else datetime.datetime.now().year
        except (TypeError, ValueError, AttributeError):
            import datetime
            selected_year = datetime.datetime.now().year

        self.selected_year = selected_year
        return ApiUsageLog.objects.filter(
            user=self.request.user,
            timestamp__year=selected_year
        ).order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        import datetime
        year = getattr(self, 'selected_year', datetime.datetime.now().year)

        total_cost = ApiUsageLog.objects.filter(
            user=self.request.user,
            timestamp__year=year
        ).aggregate(total=Sum('computed_cost'))['total'] or 0

        context['total_cost'] = total_cost
        context['year'] = year

        # Summary per CSV upload for the selected year
        context['upload_summary'] = ApiUsageLog.objects.filter(
            user=self.request.user,
            timestamp__year=year
        ).values(
            'csv_upload__id', 'csv_upload__file_name', 'csv_upload__upload_date'
        ).annotate(
            total_input_tokens=Sum('input_tokens'),
            total_output_tokens=Sum('output_tokens'),
            total_cost=Sum('computed_cost')
        ).order_by('-csv_upload__upload_date')
        return context
