import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Transaction, YearlyMonthlyUserRollup, Category, Merchant, UploadFile
from decimal import Decimal
from api.services import RollupService

@pytest.mark.django_db
class TestYearlyRollup:

    @pytest.fixture
    def logged_in_client(self, client):
        user = User.objects.create_user(username='testuser', password='password')
        client.login(username='testuser', password='password')
        return client, user

    def test_manual_transaction_updates_rollup(self, logged_in_client):
        client, user = logged_in_client
        # Initial categories are created by default sometimes, but let's be explicit
        
        url = reverse('transaction_create')
        data = {
            'amount': '50.00',
            'merchant_name': 'Pizza Express',
            'transaction_date': '2025-01-15',
            'category_name': 'Food',
        }
        
        response = client.post(url, data)
        assert response.status_code == 302
        
        rollup = YearlyMonthlyUserRollup.objects.get(user=user, by_year=2025, month_number=None)
        assert rollup.total_amount_expense_by_year == Decimal('50.00')
        assert rollup.total_amount_income_by_year == Decimal('0.00')

        month_rollup = YearlyMonthlyUserRollup.objects.get(user=user, by_year=2025, month_number=1)
        assert month_rollup.total_amount_expense_by_month == Decimal('50.00')
        assert month_rollup.total_amount_income_by_month == Decimal('0.00')

    def test_update_transaction_amount_updates_rollup(self, logged_in_client):
        client, user = logged_in_client
        category = Category.objects.create(name='Food', user=user)
        merchant = Merchant.objects.create(name='Pizza Express', user=user)
        
        tx = Transaction.objects.create(
            user=user,
            amount=Decimal('50.00'),
            transaction_date='2025-01-15',
            category=category,
            merchant=merchant,
            transaction_type='expense'
        )
        RollupService.update_user_rollup(user, [(2025, 1)])
        
        url = reverse('transaction_detail', kwargs={'pk': tx.pk})
        data = {
            'amount': '75.00',
            'transaction_date': '2025-01-15',
            'category': category.id,
            'description': 'Updated description',
            'merchant_name': 'Pizza Express',
            'category_name': 'Food'
        }
        
        response = client.post(url, data)
        assert response.status_code == 302
        
        rollup = YearlyMonthlyUserRollup.objects.get(user=user, by_year=2025, month_number=None)
        assert rollup.total_amount_expense_by_year == Decimal('75.00')

        month_rollup = YearlyMonthlyUserRollup.objects.get(user=user, by_year=2025, month_number=1)
        assert month_rollup.total_amount_expense_by_month == Decimal('75.00')

    def test_delete_transaction_updates_rollup(self, logged_in_client):
        client, user = logged_in_client
        tx = Transaction.objects.create(
            user=user,
            amount=Decimal('50.00'),
            transaction_date='2025-01-15',
            transaction_type='expense'
        )
        RollupService.update_user_rollup(user, [(2025, 1)])
        
        url = reverse('transaction_detail', kwargs={'pk': tx.pk})
        response = client.post(url, {'delete': 'true'})
        assert response.status_code == 302
        
        rollup = YearlyMonthlyUserRollup.objects.get(user=user, by_year=2025, month_number=None)
        assert rollup.total_amount_expense_by_year == Decimal('0.00')

        month_rollup = YearlyMonthlyUserRollup.objects.get(user=user, by_year=2025, month_number=1)
        assert month_rollup.total_amount_expense_by_month == Decimal('0.00')

    def test_delete_upload_updates_rollup(self, logged_in_client):
        client, user = logged_in_client
        upload = UploadFile.objects.create(user=user, file_name='test.csv')
        Transaction.objects.create(
            user=user,
            amount=Decimal('100.00'),
            transaction_date='2024-05-20',
            upload_file=upload,
            transaction_type='expense'
        )
        RollupService.update_user_rollup(user, [(2024, 5)])
        
        url = reverse('transactions_upload_delete', kwargs={'pk': upload.pk})
        response = client.post(url)
        assert response.status_code == 302
        
        rollup = YearlyMonthlyUserRollup.objects.get(user=user, by_year=2024, month_number=None)
        assert rollup.total_amount_expense_by_year == Decimal('0.00')

        month_rollup = YearlyMonthlyUserRollup.objects.get(user=user, by_year=2024, month_number=5)
        assert month_rollup.total_amount_expense_by_month == Decimal('0.00')
