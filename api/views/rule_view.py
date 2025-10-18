from django.views import View
from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpRequest, HttpResponse
import json
import logging

from agent.agent import ExpenseCategorizerAgent
from api.models import Category, Rule

logger = logging.getLogger(__name__)


class RuleDefineView(View):

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:

        user_rule_text = request.POST.get('user_rule_text', '').strip()

        if not user_rule_text:
            request.session['rule_validation_result'] = {
                'status': 'warning',
                'message': 'Il campo della regola non può essere vuoto.'
            }
            request.session['last_user_rule'] = ''
            return redirect(reverse('transaction_list'))

        try:
            agent = ExpenseCategorizerAgent(available_categories=list(Category.objects.filter(user=request.user).values_list('name', flat=True)))
            rule_result = agent.process_user_rule(user_rule_text)
            if rule_result['valid'] == 'true':
                Rule.objects.create(user=request.user, text_content=user_rule_text).save()

        except Exception as e:
            logger.error(f"Unexpected error during rule processing: {e}", exc_info=True)
            validation_result = {
                'status': 'error',
                'message': f'Errore imprevisto durante l\'elaborazione della regola.'
            }

        return redirect(reverse('transaction_list'))