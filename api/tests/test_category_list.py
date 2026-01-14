import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Category, Merchant, Transaction, CsvUpload
from datetime import date
from decimal import Decimal

@pytest.mark.django_db
class TestCategoryListView:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.category = Category.objects.create(user=self.user, name="Food")
        self.merchant = Merchant.objects.create(user=self.user, name="Supermarket")
        self.csv_upload = CsvUpload.objects.create(user=self.user, file_name="test.csv")
        
        # Jan 2025
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 1, 1),
            amount=Decimal("50.00"),
            category=self.category,
            merchant=self.merchant,
            status="categorized",
            csv_upload=self.csv_upload
        )
        
        # Feb 2025
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 2, 1),
            amount=Decimal("30.00"),
            category=self.category,
            merchant=self.merchant,
            status="categorized",
            csv_upload=self.csv_upload
        )

    def test_category_list_year_filter_only(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_list')
        
        # Currently, it should show 80.00 for 2025 because month filter is not implemented
        response = client.get(url, {'year': 2025})
        assert response.status_code == 200
        
        # We need to check the context for now as it might not be rendered in HTML yet
        categories = response.context['categories']
        food_cat = next(c for c in categories if c.name == "Food")
        assert food_cat.transaction_amount == Decimal("80.00")

    def test_category_list_month_filter_works(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_list')
        
        # Filter for Jan 2025
        response = client.get(url, {'year': 2025, 'month': 1})
        assert response.status_code == 200
        
        categories = response.context['categories']
        food_cat = next(c for c in categories if c.name == "Food")
        assert food_cat.transaction_amount == Decimal("50.00")
        assert food_cat.transaction_count == 1
        
        # Filter for Feb 2025
        response = client.get(url, {'year': 2025, 'month': 2})
        assert response.status_code == 200
        
        categories = response.context['categories']
        food_cat = next(c for c in categories if c.name == "Food")
        assert food_cat.transaction_amount == Decimal("30.00")
        assert food_cat.transaction_count == 1

    def test_category_list_amounts_displayed(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_list')
        
        response = client.get(url, {'year': 2025, 'month': 1})
        assert response.status_code == 200
        
        content = response.content.decode()
        assert "€ 50.00" in content
        assert "1 transazioni" in content
