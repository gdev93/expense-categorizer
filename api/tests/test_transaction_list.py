import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.tests.data_fixtures import create_test_data
from api.models import Transaction

@pytest.mark.django_db
class TestTransactionListView:
    def test_transaction_list_view_status_code(self, client):
        user = User.objects.create_user(username="testuser", password="password")
        client.login(username="testuser", password="password")
        create_test_data(user)
        
        url = reverse('transaction_list')
        response = client.get(url)
        
        assert response.status_code == 200

    def test_transaction_list_content(self, client):
        user = User.objects.create_user(username="testuser2", password="password")
        client.login(username="testuser2", password="password")
        data = create_test_data(user)
        
        url = reverse('transaction_list')
        response = client.get(url)
        
        assert response.status_code == 200
        # TransactionListView filters out transactions without category or merchant
        # and transaction_type='expense'
        # In create_test_data, we have:
        # 1. supermarket (food) - categorized - expense
        # 2. gas_station (transport) - categorized - expense
        # 3. electric_co (utilities) - categorized - expense
        # 4. Unknown Cafe - uncategorized - merchant=None - expense
        
        # So 3 should be in the list
        assert len(response.context['transactions']) == 3
        
        content = response.content.decode()
        assert "Supermarket" in content
        assert "Gas Station" in content
        assert "Electric Co" in content
        assert "Unknown Cafe" not in content # It's uncategorized/no merchant in the main list

    def test_transaction_list_filter_category(self, client):
        user = User.objects.create_user(username="testuser3", password="password")
        client.login(username="testuser3", password="password")
        data = create_test_data(user)
        food_category = data['categories'][0]
        
        url = reverse('transaction_list')
        response = client.get(url, {'category': food_category.id})
        
        assert response.status_code == 200
        assert len(response.context['transactions']) == 1
        assert "Supermarket" in response.content.decode()

    def test_transaction_list_search(self, client):
        user = User.objects.create_user(username="testuser4", password="password")
        client.login(username="testuser4", password="password")
        create_test_data(user)
        
        url = reverse('transaction_list')
        response = client.get(url, {'search': 'Gas Station'})
        
        assert response.status_code == 200
        assert len(response.context['transactions']) == 1
        assert "Gas Station" in response.content.decode()
