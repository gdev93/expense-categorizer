from django.urls import path
from .views import CostSummaryView

app_name = 'costs'

urlpatterns = [
    # path('summary/', CostSummaryView.as_view(), name='summary'),
]
