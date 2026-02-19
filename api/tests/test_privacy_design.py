import pytest
from django.contrib.auth.models import User
from api.models import Merchant, Transaction, Category
from api.privacy_utils import generate_blind_index, decrypt_value
from decimal import Decimal

@pytest.mark.django_db
def test_privacy_encryption_and_blind_index():
    user = User.objects.create_user(username='testuser_privacy', password='password')
    merchant_name = "Supermarket ABC"
    
    # Test Merchant encryption and blind index
    merchant = Merchant.objects.create(name=merchant_name, user=user)
    
    assert merchant.encrypted_name is not None
    assert merchant.name_hash == generate_blind_index(merchant_name)
    assert decrypt_value(merchant.encrypted_name) == merchant_name
    
    # Test Transaction encryption
    category = Category.objects.create(name="Food", user=user)
    amount = Decimal("42.50")
    description = "Groceries for the week"
    
    tx = Transaction.objects.create(
        user=user,
        merchant=merchant,
        category=category,
        amount=amount,
        description=description,
        transaction_date="2026-02-19"
    )
    
    assert tx.amount == amount
    assert tx.encrypted_description is not None
    assert decrypt_value(tx.encrypted_description) == description

@pytest.mark.django_db
def test_merchant_matching_with_blind_index():
    user = User.objects.create_user(username='testuser_matching', password='password')
    merchant_name = "Starbucks"
    merchant = Merchant.objects.create(name=merchant_name, user=user)
    
    # Matching using blind index
    merchant_hash = generate_blind_index("STARBUCKS") # Case insensitive and stripped in generate_blind_index
    match = Merchant.objects.filter(user=user, name_hash=merchant_hash).first()
    
    assert match == merchant

@pytest.mark.django_db
def test_transaction_filter_by_merchant_hash():
    from api.views.transactions.transaction_mixins import TransactionFilterMixin, TransactionFilterState
    from django.test import RequestFactory
    
    user = User.objects.create_user(username='testuser_filter', password='password')
    merchant = Merchant.objects.create(name="Target Store", user=user)
    category = Category.objects.create(name="Shopping", user=user)
    
    Transaction.objects.create(
        user=user,
        merchant=merchant,
        category=category,
        amount=Decimal("10.00"),
        description="Searchable description",
        transaction_date="2026-02-19",
        status="categorized"
    )
    
    # Setup Mixin
    class MockView(TransactionFilterMixin):
        def __init__(self, user):
            self.request = RequestFactory().get('/')
            self.request.user = user
    
    view = MockView(user)
    
    # 1. Search by exact merchant name (which view should hash)
    view.get_transaction_filters = lambda: TransactionFilterState(year=2026, months=[2], search="Target Store")
    qs = view.get_transaction_filter_query()
    assert qs.count() == 1
    assert qs.first().merchant == merchant
    
    # 2. Search by something else
    view.get_transaction_filters = lambda: TransactionFilterState(year=2026, months=[2], search="Target")
    qs = view.get_transaction_filter_query()
    assert qs.count() == 0
    
    # 3. Search by description (exact match now required due to blind index)
    view.get_transaction_filters = lambda: TransactionFilterState(year=2026, months=[2], search="Searchable description")
    qs = view.get_transaction_filter_query()
    assert qs.count() == 1

