from django.test import TestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from api.context_processors import is_free_trial, available_years_context, available_months_context, user_uploads, user_avatar

class ContextProcessorsTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_is_free_trial_anonymous_user_no_resolver(self):
        request = self.factory.get('/')
        request.user = AnonymousUser()
        
        # This should not raise
        result = is_free_trial(request)
        self.assertIn('is_free_trial', result)
        self.assertFalse(result['is_free_trial'])

    def test_is_free_trial_anonymous_user_private_view(self):
        request = self.factory.get('/private/')
        request.user = AnonymousUser()
        
        class MockResolverMatch:
            def __init__(self):
                self.func = lambda x: x
        
        request.resolver_match = MockResolverMatch()
        
        # This should NOT raise PermissionDenied
        result = is_free_trial(request)
        self.assertFalse(result['is_free_trial'])

    def test_available_years_context_anonymous_user_private_view(self):
        request = self.factory.get('/private/')
        request.user = AnonymousUser()
        class MockResolverMatch:
            def __init__(self):
                self.func = lambda x: x
        request.resolver_match = MockResolverMatch()
        
        # This should NOT raise PermissionDenied
        result = available_years_context(request)
        self.assertEqual(result['available_years'], [])

    def test_available_months_context_anonymous_user_private_view(self):
        request = self.factory.get('/private/')
        request.user = AnonymousUser()
        class MockResolverMatch:
            def __init__(self):
                self.func = lambda x: x
        request.resolver_match = MockResolverMatch()
        
        # This should NOT raise PermissionDenied
        result = available_months_context(request)
        self.assertEqual(result['available_months'], [])

    def test_user_uploads_anonymous_user_private_view(self):
        request = self.factory.get('/private/')
        request.user = AnonymousUser()
        class MockResolverMatch:
            def __init__(self):
                self.func = lambda x: x
        request.resolver_match = MockResolverMatch()
        
        # This should NOT raise PermissionDenied
        result = user_uploads(request)
        self.assertEqual(list(result['user_uploads']), [])

    def test_user_avatar_anonymous_user(self):
        request = self.factory.get('/')
        request.user = AnonymousUser()
        
        result = user_avatar(request)
        self.assertIn('user_avatar_url', result)
        self.assertIsNone(result['user_avatar_url'])

    def test_user_avatar_authenticated_no_social(self):
        from django.contrib.auth.models import User
        user = User.objects.create_user(username='testuser')
        request = self.factory.get('/')
        request.user = user
        
        result = user_avatar(request)
        self.assertIn('user_avatar_url', result)
        self.assertIsNone(result['user_avatar_url'])

    def test_user_avatar_authenticated_with_google_social(self):
        from django.contrib.auth.models import User
        from allauth.socialaccount.models import SocialAccount
        user = User.objects.create_user(username='googleuser')
        sa = SocialAccount.objects.create(user=user, provider='google', extra_data={'picture': 'http://example.com/avatar.jpg'})
        
        request = self.factory.get('/')
        request.user = user
        
        result = user_avatar(request)
        self.assertIn('user_avatar_url', result)
        # allauth's get_avatar_url might depend on various things, but it should return something if picture is in extra_data
        self.assertTrue(result['user_avatar_url'])
