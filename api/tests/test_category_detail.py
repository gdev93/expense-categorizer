import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Category, Merchant, Transaction, CsvUpload
from datetime import date
from decimal import Decimal

@pytest.mark.django_db
class TestCategoryDetailView:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.category = Category.objects.create(user=self.user, name="Food")
        self.merchant_a = Merchant.objects.create(user=self.user, name="Supermarket")
        self.merchant_b = Merchant.objects.create(user=self.user, name="Restaurant")
        self.csv_upload = CsvUpload.objects.create(user=self.user, file_name="test.csv")
        
        # Jan 2025 - Supermarket
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 1, 1),
            amount=Decimal("50.00"),
            category=self.category,
            merchant=self.merchant_a,
            description="Grocery shopping",
            status="categorized",
            csv_upload=self.csv_upload
        )
        
        # Feb 2025 - Restaurant
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 2, 1),
            amount=Decimal("30.00"),
            category=self.category,
            merchant=self.merchant_b,
            description="Dinner out",
            status="categorized",
            csv_upload=self.csv_upload
        )

        # Jan 2024 - Supermarket (different year)
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2024, 1, 1),
            amount=Decimal("20.00"),
            category=self.category,
            merchant=self.merchant_a,
            description="Old grocery",
            status="categorized",
            csv_upload=self.csv_upload
        )

    def test_category_detail_no_filter(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_detail', args=[self.category.id])
        
        response = client.get(url)
        assert response.status_code == 200
        # Should show 2 transactions (Jan 2025 and Feb 2025) because it defaults to the latest year (2025)
        assert len(response.context['transactions']) == 2

    def test_category_detail_search_filter(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_detail', args=[self.category.id])
        
        # Search for "Supermarket" - defaults to 2025
        response = client.get(url, {'search': 'Supermarket'})
        assert response.status_code == 200
        # Should show 1 transaction (Jan 2025)
        assert len(response.context['transactions']) == 1
        
        # Search for "Supermarket" in 2024
        response = client.get(url, {'search': 'Supermarket', 'year': 2024})
        assert response.status_code == 200
        # Should show 1 transaction (Jan 2024)
        assert len(response.context['transactions']) == 1

    def test_category_detail_year_filter(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_detail', args=[self.category.id])
        
        # Filter for 2025
        response = client.get(url, {'year': 2025})
        assert response.status_code == 200
        assert len(response.context['transactions']) == 2
        
        # Filter for 2024
        response = client.get(url, {'year': 2024})
        assert response.status_code == 200
        assert len(response.context['transactions']) == 1

    def test_category_detail_month_filter(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_detail', args=[self.category.id])
        
        # Filter for Jan (defaults to 2025)
        response = client.get(url, {'months': [1]})
        assert response.status_code == 200
        # Should show 1 transaction (Jan 2025)
        assert len(response.context['transactions']) == 1
        
        # Filter for Feb
        response = client.get(url, {'months': [2]})
        assert response.status_code == 200
        assert len(response.context['transactions']) == 1

    def test_category_detail_combined_filter(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_detail', args=[self.category.id])
        
        # Filter for 2025, Jan, "Supermarket"
        response = client.get(url, {'year': 2025, 'months': [1], 'search': 'Supermarket'})
        assert response.status_code == 200
        assert len(response.context['transactions']) == 1
        assert response.context['transactions'][0].transaction_date.year == 2025
        assert response.context['transactions'][0].transaction_date.month == 1
