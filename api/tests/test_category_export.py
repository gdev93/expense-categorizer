import pytest
import pandas as pd
from io import BytesIO
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Category, Transaction, Merchant, UploadFile
from datetime import date

@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="password")

@pytest.mark.django_db
def test_category_export_italian_months(client, user):
    client.force_login(user)
    
    # Create category and transactions in different months
    cat = Category.objects.create(name="Food", user=user)
    upload = UploadFile.objects.create(user=user, file_name="test.csv")
    merchant = Merchant.objects.create(name="Supermarket", user=user)
    
    # January transaction
    Transaction.objects.create(
        user=user, 
        category=cat, 
        merchant=merchant,
        upload_file=upload,
        amount=10.50,
        transaction_date=date(2025, 1, 15),
        status='categorized'
    )
    
    # February transaction
    Transaction.objects.create(
        user=user, 
        category=cat, 
        merchant=merchant,
        upload_file=upload,
        amount=20.00,
        transaction_date=date(2025, 2, 10),
        status='categorized'
    )
    
    url = reverse('category_export')
    response = client.get(url, {'year': 2025})
    
    assert response.status_code == 200
    assert response['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    
    # Load Excel content
    content = BytesIO(response.content)
    df = pd.read_excel(content)
    
    # Verify months are Italian names
    months = df['Mese'].tolist()
    assert 'Gennaio' in months
    assert 'Febbraio' in months
    # Verify they are not numbers
    assert 1 not in months
    assert 2 not in months

@pytest.mark.django_db
def test_category_export_all_if_none_selected(client, user):
    client.force_login(user)
    
    # Create multiple categories
    cat1 = Category.objects.create(name="Food", user=user)
    cat2 = Category.objects.create(name="Transport", user=user)
    
    upload = UploadFile.objects.create(user=user, file_name="test.csv")
    merchant = Merchant.objects.create(name="Merchant", user=user)
    
    # Transactions for both categories
    Transaction.objects.create(
        user=user, category=cat1, merchant=merchant, upload_file=upload,
        amount=10.00, transaction_date=date(2025, 1, 1), status='categorized'
    )
    Transaction.objects.create(
        user=user, category=cat2, merchant=merchant, upload_file=upload,
        amount=20.00, transaction_date=date(2025, 1, 1), status='categorized'
    )
    
    url = reverse('category_export')
    # No categories parameter passed
    response = client.get(url, {'year': 2025})
    
    assert response.status_code == 200
    df = pd.read_excel(BytesIO(response.content))
    
    categories = df['Categoria'].tolist()
    assert "Food" in categories
    assert "Transport" in categories

@pytest.mark.django_db
def test_category_export_selected_categories_only(client, user):
    client.force_login(user)
    
    # Create multiple categories
    cat1 = Category.objects.create(name="Food", user=user)
    cat2 = Category.objects.create(name="Transport", user=user)
    
    upload = UploadFile.objects.create(user=user, file_name="test.csv")
    merchant = Merchant.objects.create(name="Merchant", user=user)
    
    # Transactions for both categories
    Transaction.objects.create(
        user=user, category=cat1, merchant=merchant, upload_file=upload,
        amount=10.00, transaction_date=date(2025, 1, 1), status='categorized'
    )
    Transaction.objects.create(
        user=user, category=cat2, merchant=merchant, upload_file=upload,
        amount=20.00, transaction_date=date(2025, 1, 1), status='categorized'
    )
    
    url = reverse('category_export')
    # Only Food category selected
    response = client.get(url, {'year': 2025, 'categories': [cat1.id]})
    
    assert response.status_code == 200
    df = pd.read_excel(BytesIO(response.content))
    
    categories = df['Categoria'].tolist()
    assert "Food" in categories
    assert "Transport" not in categories
