import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Category, Transaction, UploadFile, Merchant
from datetime import date
from decimal import Decimal

@pytest.mark.django_db
class TestSessionFilters:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.category1 = Category.objects.create(user=self.user, name="Food")
        self.category2 = Category.objects.create(user=self.user, name="Bills")
        self.merchant = Merchant.objects.create(user=self.user, name="Test Merchant")
        self.upload_file = UploadFile.objects.create(user=self.user, file_name="test.csv")
        
        # 2025 transactions
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 1, 1),
            amount=Decimal("50.00"),
            category=self.category1,
            merchant=self.merchant,
            status="categorized",
            upload_file=self.upload_file
        )
        # 2024 transactions
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2024, 1, 1),
            amount=Decimal("100.00"),
            category=self.category2,
            merchant=self.merchant,
            status="categorized",
            upload_file=self.upload_file
        )

    def test_filter_persistence_in_session(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_list')
        
        # 1. Request with year 2024
        response = client.get(url, {'year': 2024})
        assert response.status_code == 200
        # Check that it filtered correctly (Category Bills has 2024 transaction)
        categories = response.context['categories']
        bills_cat = next(c for c in categories if c.name == "Bills")
        food_cat = next(c for c in categories if c.name == "Food")
        assert bills_cat.transaction_amount == Decimal("100.00")
        assert food_cat.transaction_amount == Decimal("0.00")
        
        # 2. Request WITHOUT year param - should still use 2024 from session
        response = client.get(url)
        assert response.status_code == 200
        categories = response.context['categories']
        bills_cat = next(c for c in categories if c.name == "Bills")
        food_cat = next(c for c in categories if c.name == "Food")
        assert bills_cat.transaction_amount == Decimal("100.00")
        assert food_cat.transaction_amount == Decimal("0.00")
        assert response.context['year'] == 2024

        # 3. Request with reset=1 - should go back to default (2025)
        response = client.get(url, {'reset': 1})
        assert response.status_code == 200
        assert response.context['year'] == 2025
        categories = response.context['categories']
        bills_cat = next(c for c in categories if c.name == "Bills")
        food_cat = next(c for c in categories if c.name == "Food")
        assert bills_cat.transaction_amount == Decimal("0.00")
        assert food_cat.transaction_amount == Decimal("50.00")

    def test_cross_page_persistence(self, client):
        client.login(username="testuser", password="password")
        
        # 1. Set year in Category List
        client.get(reverse('category_list'), {'year': 2024})
        
        # 2. Go to Transaction List - should also show 2024
        response = client.get(reverse('transaction_list'))
        assert response.status_code == 200
        assert response.context['year'] == 2024
        # Should only show the 2024 transaction
        assert len(response.context['transactions']) == 1
        assert response.context['transactions'][0].amount == Decimal("100.00")

    def test_category_detail_reset_updates_year_oob(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_detail', args=[self.category1.id])
        
        # 1. Start with 2024 in session
        client.get(url, {'year': 2024})
        
        # 2. Trigger reset via HTMX
        response = client.get(url, {'reset': '1'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='category-detail-results')
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # 3. Check if year select is swapped OOB
        assert 'id="year"' in content
        assert 'hx-swap-oob="true"' in content
        assert 'value="2025" selected' in content

    def test_category_list_reset_updates_year_oob(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_list')
        
        # 1. Start with 2024 in session
        client.get(url, {'year': 2024})
        
        # 2. Trigger reset via HTMX
        response = client.get(url, {'reset': '1'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='category-results')
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # 3. Check if header is swapped OOB (which contains the year select)
        assert 'id="stickyHeader"' in content
        assert 'hx-swap-oob="true"' in content
        assert 'value="2025" selected' in content

    def test_transaction_list_reset_updates_year_oob(self, client):
        client.login(username="testuser", password="password")
        url = reverse('transaction_list')
        
        # 1. Start with 2024 in session
        client.get(url, {'year': 2024})
        
        # 2. Trigger reset via HTMX
        response = client.get(url, {'reset': '1'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET='transaction-results')
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # 3. Check if year select is swapped OOB
        assert 'id="year-select_desktop"' in content or 'id="year-select_mobile"' in content
        assert 'hx-swap-oob="true"' in content
        assert 'value="2025" selected' in content
