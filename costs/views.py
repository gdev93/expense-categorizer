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
        return ApiUsageLog.objects.filter(user=self.request.user).order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_cost'] = CostService.get_user_total_cost(self.request.user)
        # Summary per CSV upload
        context['upload_summary'] = ApiUsageLog.objects.filter(user=self.request.user).values(
            'csv_upload__id', 'csv_upload__file_name', 'csv_upload__upload_date'
        ).annotate(
            total_input_tokens=Sum('input_tokens'),
            total_output_tokens=Sum('output_tokens'),
            total_cost=Sum('computed_cost')
        ).order_by('-csv_upload__upload_date')
        return context
