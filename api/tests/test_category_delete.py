from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from api.models import Category, Merchant, UploadFile, Transaction, Rule


@pytest.mark.django_db
class TestCategoryDeleteWithReassignment:
    def setup_method(self):
        self.user = User.objects.create_user(username="testuserdeletereassignment", password="password")
        self.category = Category.objects.create(user=self.user, name="Food")
        self.new_category = Category.objects.create(user=self.user, name="More Food")
        self.merchant_a = Merchant.objects.create(user=self.user, name="Supermarket")
        self.merchant_b = Merchant.objects.create(user=self.user, name="Restaurant")
        self.upload_file = UploadFile.objects.create(user=self.user, file_name="test.csv")
        self.rule = Rule.objects.create(user=self.user, category=self.category, merchant=self.merchant_a)

        # Jan 2025 - Supermarket
        Transaction.objects.create(
            user=self.user,
            transaction_date=date(2025, 1, 1),
            amount=Decimal("50.00"),
            category=self.category,
            merchant=self.merchant_a,
            description="Grocery shopping",
            status="categorized",
            upload_file=self.upload_file
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
            upload_file=self.upload_file
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
            upload_file=self.upload_file
        )

    def test_category_delete_reassignment(self, client):
        client.login(username=self.user.username, password="password")
        url = reverse('category_delete', args=[self.category.id])
        data = {
            'replacement_category': self.new_category.id
        }
        client.post(url, data)
        assert not Transaction.objects.filter(user = self.user, category=self.category).exists()
        assert not Rule.objects.filter(category=self.category).exists()
        assert Transaction.objects.filter(category=self.new_category).exists()
        assert len(Transaction.objects.filter(category=self.new_category)) == 3
        assert len(Rule.objects.filter(category=self.new_category)) == 1

    def test_category_delete_new_category_creation(self, client):
        client.login(username=self.user.username, password="password")
        url = reverse('category_delete', args=[self.category.id])
        data = {
            'new_category_name': 'Brand New Category'
        }
        client.post(url, data)
        assert not Category.objects.filter(name="Food").exists()
        new_cat = Category.objects.get(name='Brand New Category')
        assert Transaction.objects.filter(category=new_cat).count() == 3
        assert Rule.objects.filter(category=new_cat).count() == 1