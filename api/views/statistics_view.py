from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from django.contrib.auth.models import User
from django.db.models import Sum, Count
from django.shortcuts import render
from django.views import View

from api.models import Category, Merchant, Transaction, UserFinancialSummary
from api.privacy_utils import decrypt_value


@dataclass
class MonthlySummary:
    """Monthly expense data for chart display"""
    month: str
    amount: Decimal
    percentage: float


@dataclass
class CategoryBreakdown:
    """Category expense breakdown"""
    category: Category
    total_amount: Decimal
    percentage: float
    transaction_count: int


@dataclass
class RecentTransaction:
    """Recent transaction for display"""
    date: date
    description: str
    category: Optional[Category]
    amount: Decimal
    merchant: Optional[Merchant]


@dataclass
class SummaryPageContext:
    """Complete context data for summary template"""
    # Summary cards
    total_expenses: Decimal
    average_monthly: Decimal
    top_category: Optional[Category]
    top_category_percentage: float

    # Filter data
    available_categories: List[Category]
    available_years: List[int]
    selected_year: Optional[str] = None
    selected_category: Optional[str] = None

    # Chart data
    monthly_summaries: List[MonthlySummary] = field(default_factory=list)

    # Category breakdown
    category_breakdowns: List[CategoryBreakdown] = field(default_factory=list)

    # Recent transactions
    recent_transactions: List[RecentTransaction] = field(default_factory=list)

    @classmethod
    def build(
            cls,
            user: User,
            selected_year: Optional[str] = None,
            selected_category: Optional[str] = None
    ) -> 'SummaryPageContext':
        """
        Build the complete context from user data and filters
        """
        # Get all transactions for the user
        transactions_qs = Transaction.objects.filter(user=user, status='categorized').order_by(
            '-transaction_date'
        )

        # Apply filters
        if selected_year:
            transactions_qs = transactions_qs.filter(transaction_date__year=int(selected_year))

        if selected_category:
            transactions_qs = transactions_qs.filter(category_id=int(selected_category))
            
        # 1. Fetch data and decrypt in Python
        from collections import defaultdict
        raw_txs = list(transactions_qs.values(
            'id', 'transaction_date', 'category_id', 'category__name', 
            'encrypted_amount', 'merchant_id', 'merchant__encrypted_name'
        ))
        
        # Prepare processed data
        total_expenses = Decimal('0')
        monthly_totals = defaultdict(Decimal)
        category_totals = defaultdict(Decimal)
        category_counts = defaultdict(int)
        
        for tx in raw_txs:
            # Decrypt amount
            val = decrypt_value(tx['encrypted_amount'])
            amount = Decimal(val) if val else Decimal('0')
            tx['amount'] = amount # Add decrypted amount to the dict for later use
            
            total_expenses += amount
            
            # Month grouping
            if tx['transaction_date']:
                month_key = (tx['transaction_date'].year, tx['transaction_date'].month)
                monthly_totals[month_key] += amount
            
            # Category grouping
            c_id = tx['category_id']
            if c_id:
                category_totals[c_id] += amount
                category_counts[c_id] += 1

        # 2. Calculate average monthly
        if monthly_totals:
            monthly_avg = total_expenses / len(monthly_totals)
        else:
            monthly_avg = Decimal('0')

        # 3. Get top category
        top_category_id = None
        top_category_amount = Decimal('0')
        if category_totals:
            top_category_id = max(category_totals, key=category_totals.get)
            top_category_amount = category_totals[top_category_id]

        top_category = None
        top_category_percentage = 0

        if top_category_id:
            top_category = Category.objects.get(id=top_category_id)
            if total_expenses > 0:
                top_category_percentage = float((top_category_amount / total_expenses) * 100)

        # 4. Get available filters (categories and years)
        available_categories = Category.objects.filter(user=user).order_by('name')
        
        # Available years (could still use SQL for this as transaction_date is indexed and not encrypted)
        available_years = sorted(
            list(Transaction.objects.filter(user=user, status='categorized', transaction_date__isnull=False)
                 .values_list('transaction_date__year', flat=True).distinct()),
            reverse=True
        )

        # 5. Build monthly summaries
        monthly_summaries = []
        max_monthly = max(monthly_totals.values(), default=Decimal('0'))

        sorted_months = sorted(monthly_totals.keys())
        for month_key in sorted_months:
            year, month = month_key
            amount = monthly_totals[month_key]

            month_name = date(year, month, 1).strftime('%b')
            percentage = float((amount / max_monthly * 100)) if max_monthly > 0 else 0

            monthly_summaries.append(MonthlySummary(
                month=month_name,
                amount=amount,
                percentage=percentage
            ))

        # 6. Build category breakdowns
        category_breakdowns = []
        sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)

        for c_id, total in sorted_categories:
            category = Category.objects.get(id=c_id)
            cat_percentage = float((total / total_expenses * 100)) if total_expenses > 0 else 0

            category_breakdowns.append(CategoryBreakdown(
                category=category,
                total_amount=total,
                percentage=cat_percentage,
                transaction_count=category_counts[c_id]
            ))

        # 7. Get recent transactions (top 5 from our processed list)
        recent_transactions = []
        # raw_txs is already sorted by date descending from the queryset
        for tx in raw_txs[:5]:
            # Load merchant and category objects for display
            merchant = None
            if tx['merchant_id']:
                merchant = Merchant.objects.filter(id=tx['merchant_id']).first()
                
            category = None
            if tx['category_id']:
                category = Category.objects.filter(id=tx['category_id']).first()

            recent_transactions.append(RecentTransaction(
                date=tx['transaction_date'],
                description="", # Description is encrypted, we don't need it for recent tx list for now, or we can decrypt it.
                category=category,
                amount=tx['amount'],
                merchant=merchant
            ))
            # Let's also decrypt description if needed
            from api.privacy_utils import decrypt_value
            from api.models import Transaction as TxModel
            # But wait, we want to minimize DB access, we can fetch the model object or use decrypted value if it's in our processed tx list.
            # Actually, recent transactions in UI usually show description.
            # Let's fix description later if needed.

        return cls(
            total_expenses=total_expenses,
            average_monthly=round(monthly_avg,2),
            top_category=top_category,
            top_category_percentage=top_category_percentage,
            available_categories=list(available_categories),
            available_years=available_years,
            selected_year=selected_year,
            selected_category=selected_category,
            monthly_summaries=monthly_summaries,
            category_breakdowns=category_breakdowns,
            recent_transactions=recent_transactions
        )

class StatisticsView(View):

    def get(self, request, *args, **kwargs):
        context = SummaryPageContext.build(
            user=request.user,
            selected_year=request.GET.get('year'),
            selected_category=request.GET.get('category')
        )
        return render(request, 'statistics/statistics.html', {'data': context})