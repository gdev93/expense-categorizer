import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Transaction, Category, Merchant, UploadFile
import datetime

@pytest.mark.django_db
class TestTransactionApplyAll:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.other_user = User.objects.create_user(username="otheruser", password="password")
        
        self.cat1 = Category.objects.create(name="Food", user=self.user)
        self.cat2 = Category.objects.create(name="Shopping", user=self.user)
        self.other_cat = Category.objects.create(name="Other", user=self.other_user)
        
        self.merchant = Merchant.objects.create(name="Amazon", user=self.user)
        self.other_merchant = Merchant.objects.create(name="eBay", user=self.user)
        
        self.upload = UploadFile.objects.create(user=self.user, file_name="test.csv")
        
    def test_apply_to_all_functionality(self, client):
        client.login(username="testuser", password="password")
        
        # 1. Create several transactions for Amazon
        t1 = Transaction.objects.create(
            user=self.user,
            merchant=self.merchant,
            merchant_raw_name="Amazon",
            category=self.cat2,
            transaction_date=datetime.date(2025, 1, 1),
            amount=10.0,
            status='categorized',
            upload_file=self.upload
        )
        t2 = Transaction.objects.create(
            user=self.user,
            merchant=self.merchant,
            merchant_raw_name="Amazon",
            category=self.cat2,
            transaction_date=datetime.date(2025, 1, 5),
            amount=20.0,
            status='categorized',
            upload_file=self.upload
        )
        # Target transaction (the one we will update)
        t3 = Transaction.objects.create(
            user=self.user,
            merchant=self.merchant,
            merchant_raw_name="Amazon",
            category=self.cat2,
            transaction_date=datetime.date(2025, 1, 10),
            amount=30.0,
            status='categorized',
            upload_file=self.upload
        )
        # Future transaction (should not be updated)
        t4 = Transaction.objects.create(
            user=self.user,
            merchant=self.merchant,
            merchant_raw_name="Amazon",
            category=self.cat2,
            transaction_date=datetime.date(2025, 1, 15),
            amount=40.0,
            status='categorized',
            upload_file=self.upload
        )
        # Different merchant (should not be updated)
        t5 = Transaction.objects.create(
            user=self.user,
            merchant=self.other_merchant,
            merchant_raw_name="eBay",
            category=self.cat2,
            transaction_date=datetime.date(2025, 1, 1),
            amount=50.0,
            status='categorized',
            upload_file=self.upload
        )
        
        # Now update t3 and set apply_to_all=true
        url = reverse('transaction_detail', kwargs={'pk': t3.pk})
        response = client.post(url, {
            'transaction_date': '2025-01-10',
            'amount': '30.00',
            'merchant_raw_name': 'Amazon',
            'description': 'Target transaction',
            'category': self.cat1.id,
            'apply_to_all': 'true'
        })
        
        assert response.status_code == 302 # It renders the template again on success
        
        # Verify t3 is updated
        t3.refresh_from_db()
        assert t3.category == self.cat1
        
        # Verify t1 and t2 are updated (previous transactions of same merchant)
        t1.refresh_from_db()
        t2.refresh_from_db()
        assert t1.category == self.cat1
        assert t2.category == self.cat1
        t4.refresh_from_db()
        assert t4.category == self.cat1

        # Verify t5 is NOT updated (different merchant)
        t5.refresh_from_db()
        assert t5.category == self.cat2

    def test_apply_to_all_security(self, client):
        # Verify it doesn't affect other user's transactions
        client.login(username="testuser", password="password")
        
        # Transaction for Amazon by other user
        other_merchant = Merchant.objects.create(name="Amazon", user=self.other_user)
        other_upload = UploadFile.objects.create(user=self.other_user, file_name="other.csv")
        t_other = Transaction.objects.create(
            user=self.other_user,
            merchant=other_merchant,
            merchant_raw_name="Amazon",
            category=self.other_cat,
            transaction_date=datetime.date(2025, 1, 1),
            amount=10.0,
            status='categorized',
            upload_file=other_upload
        )
        
        # My transaction for Amazon
        t_me = Transaction.objects.create(
            user=self.user,
            merchant=self.merchant,
            merchant_raw_name="Amazon",
            category=self.cat2,
            transaction_date=datetime.date(2025, 1, 10),
            amount=30.0,
            status='categorized',
            upload_file=self.upload
        )
        
        url = reverse('transaction_detail', kwargs={'pk': t_me.pk})
        client.post(url, {
            'transaction_date': '2025-01-10',
            'amount': '30.00',
            'merchant_raw_name': 'Amazon',
            'description': 'My transaction',
            'category': self.cat1.id,
            'apply_to_all': 'true'
        })
        
        # Verify my transaction is updated
        t_me.refresh_from_db()
        assert t_me.category == self.cat1
        
        # Verify other user's transaction is NOT updated
        t_other.refresh_from_db()
        assert t_other.category == self.other_cat
