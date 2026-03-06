import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Transaction, Category, UploadFile
import datetime

@pytest.mark.django_db
class TestTransactionDelete:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.cat1 = Category.objects.create(name="Food", user=self.user)
        self.upload = UploadFile.objects.create(user=self.user, file_name="test.csv")
        self.transaction = Transaction.objects.create(
            user=self.user,
            amount=10.0,
            transaction_date=datetime.date(2025, 1, 1),
            category=self.cat1,
            upload_file=self.upload,
            status='categorized'
        )

    def test_delete_transaction(self, client):
        client.login(username="testuser", password="password")
        url = reverse('transaction_detail', kwargs={'pk': self.transaction.pk})
        
        # Verify transaction exists
        assert Transaction.objects.filter(pk=self.transaction.pk).exists()
        
        # Send post request with delete=True
        # This simulates the hidden input I added
        response = client.post(url, {'delete': 'true'})
        
        # Should redirect to transaction list
        assert response.status_code == 302
        assert response.url == reverse('transaction_list')
        
        # Verify transaction is deleted
        assert not Transaction.objects.filter(pk=self.transaction.pk).exists()

    def test_delete_transaction_unauthorized(self, client):
        # Create another user
        other_user = User.objects.create_user(username="otheruser", password="password")
        client.login(username="otheruser", password="password")
        
        url = reverse('transaction_detail', kwargs={'pk': self.transaction.pk})
        
        # Should return 404 because get_queryset filters by user
        response = client.post(url, {'delete': 'true'})
        assert response.status_code == 404
        
        # Verify transaction is NOT deleted
        assert Transaction.objects.filter(pk=self.transaction.pk).exists()
