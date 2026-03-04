from django.urls import path
from .views.costs.cost_summary import CostSummaryView

app_name = 'costs'

urlpatterns = [
    # path('summary/', CostSummaryView.as_view(), name='summary'),
]
