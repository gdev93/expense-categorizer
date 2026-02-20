import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.tests.data_fixtures import create_test_data
from decimal import Decimal

@pytest.mark.django_db
class TestTransactionAmountFilter:
    def test_transaction_list_filter_amount(self, client):
        user = User.objects.create_user(username="amountuser", password="password")
        client.login(username="amountuser", password="password")
        create_test_data(user)
        
        url = reverse('transaction_list')
        # Search for amount 100.00
        response = client.get(url, {'amount': '100.00'})
        
        assert response.status_code == 200
        # If it doesn't work, it will return all 3 categorized transactions
        # If it works, it should return only 1
        assert len(response.context['transactions']) == 1
        assert "Electric Co" in response.content.decode()

    def test_transaction_list_filter_amount_not_found(self, client):
        user = User.objects.create_user(username="amountuser2", password="password")
        client.login(username="amountuser2", password="password")
        create_test_data(user)
        
        url = reverse('transaction_list')
        # Search for amount that doesn't exist
        response = client.get(url, {'amount': '99.99'})
        
        assert response.status_code == 200
        assert len(response.context['transactions']) == 0
