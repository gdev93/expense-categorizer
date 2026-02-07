import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import Transaction, Merchant, Category
from decimal import Decimal
from datetime import date

@pytest.mark.django_db
def test_merchant_view_pagination(client):
    user = User.objects.create_user(username="testuser_merchant", password="password")
    client.login(username="testuser_merchant", password="password")
    
    category = Category.objects.create(user=user, name="Category")
    
    # Create 30 different merchants to trigger pagination (default 25)
    # All these will be categorized
    merchants = []
    for i in range(30):
        m = Merchant.objects.create(user=user, name=f"Merchant {i:02d}")
        merchants.append(m)
        Transaction.objects.create(
            user=user,
            transaction_date=date(2025, 1, 1),
            amount=Decimal("10.00"),
            description=f"Transaction {i}",
            merchant=m,
            category=category,
            status="categorized"
        )
    
    # Create 2 merchants with uncategorized transactions
    uncat_merchant_1 = Merchant.objects.create(user=user, name="Uncat Merchant 1")
    Transaction.objects.create(
        user=user,
        transaction_date=date(2025, 1, 1),
        amount=Decimal("5.00"),
        description="Uncat 1",
        merchant=uncat_merchant_1,
        status="uncategorized"
    )
    
    uncat_merchant_2 = Merchant.objects.create(user=user, name="Uncat Merchant 2")
    Transaction.objects.create(
        user=user,
        transaction_date=date(2025, 1, 1),
        amount=Decimal("7.00"),
        description="Uncat 2",
        merchant=uncat_merchant_2,
        status="uncategorized"
    )

    url = reverse('transaction_list')
    # Use merchant view
    response = client.get(url, {'view_type': 'merchant'})
    
    assert response.status_code == 200
    assert response.context['view_type'] == 'merchant'
    
    # Check if uncategorized merchants are separated
    assert 'uncategorized_merchants' in response.context
    assert len(response.context['uncategorized_merchants']) == 2
    
    # Check if paginated categorized list is correct
    assert 'merchant_summary' in response.context
    merchant_summary = response.context['merchant_summary']
    
    # We have 30 categorized merchants. Default pagination is 25.
    assert len(merchant_summary) == 25
    assert response.context['is_paginated'] is True
    
    # Ensure uncat merchants are NOT in the main list
    main_list_names = [m['merchant__name'] for m in merchant_summary]
    assert "Uncat Merchant 1" not in main_list_names
    assert "Uncat Merchant 2" not in main_list_names

    # UI Check: verify pagination shows up in HTML
    content = response.content.decode()
    assert "Pagina 1 di 2" in content
    assert "Successiva ›" in content

    # Check if next page works
    response_page2 = client.get(url, {'view_type': 'merchant', 'page': 2})
    assert response_page2.status_code == 200
    assert len(response_page2.context['merchant_summary']) == 5

    # UI Check for page 2
    content_page2 = response_page2.content.decode()
    assert "Pagina 2 di 2" in content_page2
    assert "‹ Precedente" in content_page2
