import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch
from api.models import Category, Transaction, Rule, UploadFile

@pytest.mark.django_db
class TestUserDetailView:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="password")
        self.url = reverse('user_profile')

    def test_get_user_detail_authenticated(self, client):
        client.login(username=self.user.username, password="password")
        
        # Create some data
        Category.objects.create(user=self.user, name="Test Category")
        upload = UploadFile.objects.create(user=self.user, file_name="test.csv", status="completed")
        Transaction.objects.create(user=self.user, amount=10.0, description="Test Tx", upload_file=upload)
        Rule.objects.create(user=self.user, text_content="Test Rule")
        
        response = client.get(self.url)
        assert response.status_code == 200
        content = response.content.decode()
        assert self.user.username in content
        
        assert reverse('user_delete') in content
        assert any("api/user/detail.html" in t.name for t in response.templates)

    def test_get_user_detail_anonymous_redirects(self, client):
        response = client.get(self.url)
        assert response.status_code == 302
        assert "login" in response.url

@pytest.mark.django_db
class TestUserDeleteView:
    def setup_method(self):
        self.user = User.objects.create_user(username="testdeleteuser", email="test@example.com", password="password")
        self.url = reverse('user_delete')

    def test_get_delete_confirm(self, client):
        client.login(username=self.user.username, password="password")
        response = client.get(self.url)
        assert response.status_code == 200
        assert "test@example.com" in response.content.decode()
        # Check that the template is used
        assert any("api/user/delete_confirm.html" in t.name for t in response.templates)

    @patch('api.views.user_views.delete_user_data.delay')
    def test_post_delete_confirm_triggers_task(self, mock_delete_task, client):
        client.login(username=self.user.username, password="password")
        response = client.post(self.url)
        
        # Verify redirect
        assert response.status_code == 302
        assert response.url == reverse('entry_point')
        
        # Verify task triggered
        mock_delete_task.assert_called_once_with(self.user.id)
        
        # Verify user logged out (session check)
        # In Django testing, we need to refresh the session from the client
        assert '_auth_user_id' not in client.session
