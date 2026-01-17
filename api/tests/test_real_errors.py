import pytest
import requests
from django.urls import reverse

@pytest.mark.django_db
def test_real_404_error(live_server):
    """
    Test that a real 404 error triggers our custom template.
    We use the live_server fixture to hit the server from outside.
    """
    url = f"{live_server.url}/path-that-does-not-exist"
    response = requests.get(url)
    
    assert response.status_code == 404
    # Check for content in our custom 404.html template (Italian)
    assert "404" in response.text
    assert "Pagina non trovata" in response.text

@pytest.mark.django_db
def test_real_403_error(live_server):
    """
    Test that a real 403 error triggers our custom template.
    """
    url = f"{live_server.url}{reverse('test_403')}"
    response = requests.get(url)
    
    assert response.status_code == 403
    assert "403" in response.text
    assert "Accesso negato" in response.text

@pytest.mark.django_db
def test_real_500_error(live_server, settings):
    """
    Test that a real 500 error triggers our custom template.
    We must ensure DEBUG is False for the custom handler to trigger.
    """
    settings.DEBUG = False
    url = f"{live_server.url}{reverse('test_500')}"
    response = requests.get(url)
    
    assert response.status_code == 500
    assert "500" in response.text
    assert "Errore interno del server" in response.text

@pytest.mark.django_db
def test_real_csrf_failure(live_server):
    """
    Test that a CSRF failure triggers our custom template.
    We send a POST request without a token to a view that requires it.
    """
    # Use a view that definitely requires POST and CSRF verification.
    url = f"{live_server.url}{reverse('authenticate_user')}"
    # Sending POST without CSRF token
    response = requests.post(url)
    
    assert response.status_code == 403
    assert "403" in response.text
    assert "Verifica di sicurezza fallita" in response.text

@pytest.mark.django_db
def test_real_502_error(live_server, settings):
    """
    Test that a real 502 error triggers our custom template via the test trigger.
    """
    settings.DEBUG = False
    url = f"{live_server.url}{reverse('test_502')}"
    response = requests.get(url)

    assert response.status_code == 502
    assert "502" in response.text
    assert "Bad Gateway" in response.text
