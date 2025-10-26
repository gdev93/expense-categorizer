import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View

from api.models import Rule, Category, Merchant

logger = logging.getLogger(__name__)


class RuleDefineView(View):

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        merchant_name = request.POST.get('merchant_name', '')
        category_name = request.POST.get('category_name', '')

        # Get or create the merchant - unpack the tuple
        merchant, created = Merchant.objects.get_or_create(name=merchant_name)

        # Get or create the category with user
        category, _ = Category.objects.get_or_create(name=category_name, user=request.user)

        # Create the rule text
        rule_text = f"Tutte le operazioni che riguardano {merchant_name}, o che compare in qualunque forma il {merchant_name}, verranno categorizzate in {category_name}"

        # Create the rule
        Rule.objects.create(
            user=request.user,
            text_content=rule_text,
            category=category,
            merchant=merchant
        )

        return redirect(reverse('transaction_list'))