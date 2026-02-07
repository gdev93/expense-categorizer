import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.tests.data_fixtures import create_test_data

@pytest.mark.django_db
class TestPagination:
    def test_pagination_desktop_default(self, client):
        user = User.objects.create_user(username="testuser_pagination", password="password")
        client.login(username="testuser_pagination", password="password")
        create_test_data(user)
        
        url = reverse('transaction_list')
        # Simulate Desktop User-Agent
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        response = client.get(url, HTTP_USER_AGENT=user_agent)
        
        assert response.status_code == 200
        assert response.context['paginate_by'] == 25

    def test_pagination_mobile_default(self, client):
        user = User.objects.create_user(username="testuser_pagination_mobile", password="password")
        client.login(username="testuser_pagination_mobile", password="password")
        create_test_data(user)
        
        url = reverse('transaction_list')
        # Simulate Mobile User-Agent
        user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1"
        response = client.get(url, HTTP_USER_AGENT=user_agent)
        
        assert response.status_code == 200
        assert response.context['paginate_by'] == 10

    def test_pagination_query_param_override(self, client):
        user = User.objects.create_user(username="testuser_pagination_override", password="password")
        client.login(username="testuser_pagination_override", password="password")
        create_test_data(user)
        
        url = reverse('transaction_list')
        # Even with Mobile User-Agent, query param should override
        user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1"
        response = client.get(url, {'paginate_by': '50'}, HTTP_USER_AGENT=user_agent)
        
        assert response.status_code == 200
        assert response.context['paginate_by'] == 50

    def test_category_detail_pagination_mobile(self, client):
        user = User.objects.create_user(username="testuser_cat_pagination", password="password")
        client.login(username="testuser_cat_pagination", password="password")
        data = create_test_data(user)
        category = data['categories'][0]
        
        url = reverse('category_detail', kwargs={'pk': category.id})
        # Simulate Mobile User-Agent
        user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1"
        response = client.get(url, HTTP_USER_AGENT=user_agent)
        
        assert response.status_code == 200
        assert response.context['paginate_by'] == 10
