from django.test import TestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from api.context_processors import is_free_trial

class ContextProcessorsTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_is_free_trial_anonymous_user(self):
        request = self.factory.get('/')
        request.user = AnonymousUser()
        
        # This should not raise TypeError
        result = is_free_trial(request)
        self.assertIn('is_free_trial', result)
        self.assertFalse(result['is_free_trial'])
