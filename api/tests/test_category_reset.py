import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Category, Merchant, Transaction, UploadFile
from datetime import date
from decimal import Decimal

@pytest.mark.django_db
class TestCategoryResetIssue:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.category = Category.objects.create(user=self.user, name="Food")
        self.merchant = Merchant.objects.create(user=self.user, name="Supermarket")
        self.upload_file = UploadFile.objects.create(user=self.user, file_name="test.csv")
        
        # 2024 Transaction
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2024, 1, 1),
            amount=Decimal("100.00"),
            category=self.category,
            merchant=self.merchant,
            status="categorized",
            upload_file=self.upload_file
        )
        
        # 2025 Transaction
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 2, 1), # February
            amount=Decimal("200.00"),
            category=self.category,
            merchant=self.merchant,
            status="categorized",
            upload_file=self.upload_file
        )

    def test_view_logic_handles_year_month_correctly(self, client):
        client.login(username="testuser", password="password")
        url = reverse('category_list')
        
        # Filter for 2024, no month
        response = client.get(url, {'year': 2024})
        assert response.status_code == 200
        cat_2024 = next(c for c in response.context['categories'] if c.name == "Food")
        assert cat_2024.transaction_amount == Decimal("100.00")
        
        # Filter for 2025, no month
        response = client.get(url, {'year': 2025})
        assert response.status_code == 200
        cat_2025 = next(c for c in response.context['categories'] if c.name == "Food")
        assert cat_2025.transaction_amount == Decimal("200.00")
        
        # Filter for 2025, month 2
        response = client.get(url, {'year': 2025, 'month': 2})
        assert response.status_code == 200
        cat_2025_m2 = next(c for c in response.context['categories'] if c.name == "Food")
        assert cat_2025_m2.transaction_amount == Decimal("200.00")

        # Filter for 2025, month 1 (where only 2024 has data)
        response = client.get(url, {'year': 2025, 'month': 1})
        assert response.status_code == 200
        cat_2025_m1 = next(c for c in response.context['categories'] if c.name == "Food")
        assert cat_2025_m1.transaction_amount == Decimal("0.00")
