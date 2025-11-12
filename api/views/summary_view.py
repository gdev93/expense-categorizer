from django.shortcuts import render
from django.views import View


class SummaryView(View):

    def get(self, request, *args, **kwargs):
        return render(request=request, template_name='summary/summary.html')