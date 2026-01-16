from django.test import TestCase, override_settings

class ErrorHandlerTest(TestCase):
    @override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
    def test_404_handler(self):
        response = self.client.get('/non-existent-url/')
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'errors/404.html')

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
    def test_403_handler(self):
        from api.views.error_views import error_403
        from django.http import HttpRequest
        from django.contrib.auth.models import AnonymousUser
        request = HttpRequest()
        request.user = AnonymousUser()
        request.GET = {}
        response = error_403(request, Exception())
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "403", status_code=403)
        self.assertContains(response, "Accesso negato", status_code=403)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
    def test_500_handler(self):
        from api.views.error_views import error_500
        from django.http import HttpRequest
        from django.contrib.auth.models import AnonymousUser
        request = HttpRequest()
        request.user = AnonymousUser()
        request.GET = {}
        response = error_500(request)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "500", status_code=500)
        self.assertContains(response, "Errore interno del server", status_code=500)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'])
    def test_csrf_failure_handler(self):
        from api.views.error_views import csrf_failure
        from django.http import HttpRequest
        from django.contrib.auth.models import AnonymousUser
        request = HttpRequest()
        request.user = AnonymousUser()
        request.GET = {}
        response = csrf_failure(request, reason="CSRF token missing")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "403", status_code=403)
        self.assertContains(response, "Verifica di sicurezza fallita", status_code=403)
