import pytest

@pytest.mark.django_db
class TestPWA:
    def test_sw_js(self, client):
        response = client.get("/sw.js")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/javascript"
        assert b"Service worker is being installed" in response.content

    def test_manifest_json(self, client):
        response = client.get("/manifest.json")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        assert b"Pecuniam" in response.content
        assert b"/static/icons/icon-192x192.svg" in response.content
