from django.views import View
from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpRequest, HttpResponse
import json
import logging

from agent.agent import ExpenseCategorizerAgent
from api.models import Category, Rule

logger = logging.getLogger(__name__)


class CategoryUpdateView(View):

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        category_id = request.POST.get('id', '')
        if not category_id:
            return redirect(reverse('transaction_list'))
        category_name = request.POST.get('name', '').strip()
        if not category_name:
            return redirect(reverse('transaction_list'))
        Category.objects.filter(id=category_id).update(name=category_name)
        return redirect(reverse('transaction_list'))