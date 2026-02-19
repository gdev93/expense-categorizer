from django.contrib.auth.models import User
from api.models import Category, Merchant, Transaction, UploadFile
from datetime import date
from decimal import Decimal

def create_test_data(user):
    # Create some categories
    food = Category.objects.create(user=user, name="Food")
    transport = Category.objects.create(user=user, name="Transport")
    utilities = Category.objects.create(user=user, name="Utilities")
    
    # Create some merchants
    supermarket = Merchant.objects.create(user=user, name="Supermarket")
    gas_station = Merchant.objects.create(user=user, name="Gas Station")
    electric_co = Merchant.objects.create(user=user, name="Electric Co")
    
    # Create a CSV upload
    upload_file = UploadFile.objects.create(user=user, file_name="test.csv", dimension=1024)
    
    # Create transactions
    transactions = [
        Transaction(
            user=user,
            transaction_date=date(2025, 1, 1),
            amount=Decimal("50.00"),
            description="Weekly groceries",
            merchant=supermarket,
            category=food,
            status="categorized",
            upload_file=upload_file
        ),
        Transaction(
            user=user,
            transaction_date=date(2025, 1, 5),
            amount=Decimal("40.00"),
            description="Gas refill",
            merchant=gas_station,
            category=transport,
            status="categorized",
            upload_file=upload_file
        ),
        Transaction(
            user=user,
            transaction_date=date(2025, 1, 10),
            amount=Decimal("100.00"),
            description="Monthly bill",
            merchant=electric_co,
            category=utilities,
            status="categorized",
            upload_file=upload_file
        ),
        Transaction(
            user=user,
            transaction_date=date(2025, 1, 15),
            amount=Decimal("15.50"),
            description="Lunch",
            status="uncategorized",
            upload_file=upload_file
        )
    ]
    Transaction.objects.bulk_create(transactions)
    
    return {
        "categories": [food, transport, utilities],
        "merchants": [supermarket, gas_station, electric_co],
        "transactions": transactions,
        "upload_file": upload_file
    }
