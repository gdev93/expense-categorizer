import logging

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DeleteView

from api.models import Rule, Category, Merchant

logger = logging.getLogger(__name__)

class RuleDeleteView(DeleteView):
    model = Rule
    success_url = reverse_lazy('transaction_list')

class RuleDefineView(View):

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        merchant_name = request.POST.get('merchant_name', '')
        category_name = request.POST.get('category_name', '')

        # Get or create the merchant - unpack the tuple
        merchant, created = Merchant.objects.get_or_create(name=merchant_name, user=request.user)

        # Get or create the category with user
        category, _ = Category.objects.get_or_create(name=category_name, user=request.user)

        create_rule(merchant, category, request.user)

        return redirect(reverse('transaction_list'))


def create_rule(merchant: Merchant, category: Category, user: User):
    Rule.objects.filter(user=user, merchant=merchant).delete()
    rule_text = f"Tutte le operazioni che riguardano {merchant.name}, o che compare in qualunque forma il {merchant.name}, verranno categorizzate in {category.name}"

    # Create the rule
    Rule.objects.create(
        user=user,
        text_content=rule_text,
        category=category,
        merchant=merchant
    )
