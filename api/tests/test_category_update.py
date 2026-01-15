import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Category

@pytest.mark.django_db
class TestCategoryUpdateView:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.category = Category.objects.create(user=self.user, name="Old Name")

    def test_category_update_redirect(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_update', args=[self.category.id])
        data = {
            'name': 'New Name',
            'description': 'Updated description'
        }
        response = client.post(url, data)
        
        # Verify redirect to category_detail instead of category_list
        expected_url = reverse('category_detail', args=[self.category.id])
        assert response.status_code == 302
        assert response.url == expected_url
        
        # Verify update happened
        self.category.refresh_from_db()
        assert self.category.name == "New Name"
