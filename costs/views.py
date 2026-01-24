from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import ApiUsageLog, CostConfiguration
from .services import CostService
from django.db.models import Sum

class CostSummaryView(LoginRequiredMixin, ListView):
    model = ApiUsageLog
    template_name = 'costs/summary.html'
    context_object_name = 'logs'

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            return ['costs/components/summary_results.html']
        return [self.template_name]

    def _get_year_and_month(self):
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

        try:
            get_month = self.request.GET.get('month')
            selected_month = int(get_month) if get_month else None
        except (TypeError, ValueError):
            selected_month = None

        return selected_year, selected_month

    def get_queryset(self):
        selected_year, selected_month = self._get_year_and_month()
        
        queryset = ApiUsageLog.objects.filter(
            user=self.request.user,
            timestamp__year=selected_year
        )
        if selected_month:
            queryset = queryset.filter(timestamp__month=selected_month)
        
        return queryset.order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_year, selected_month = self._get_year_and_month()

        filter_kwargs = {
            'user': self.request.user,
            'timestamp__year': selected_year
        }
        if selected_month:
            filter_kwargs['timestamp__month'] = selected_month

        total_cost = ApiUsageLog.objects.filter(
            **filter_kwargs
        ).aggregate(total=Sum('computed_cost'))['total'] or 0

        context['total_cost'] = total_cost
        context['year'] = selected_year
        context['month'] = selected_month

        # Summary per CSV upload for the selected year/month
        context['upload_summary'] = ApiUsageLog.objects.filter(
            **filter_kwargs
        ).values(
            'upload_file__id', 'upload_file__file_name', 'upload_file__upload_date'
        ).annotate(
            total_input_tokens=Sum('input_tokens'),
            total_output_tokens=Sum('output_tokens'),
            total_cost=Sum('computed_cost')
        ).order_by('-upload_file__upload_date')
        return context
