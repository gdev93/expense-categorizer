from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from django.contrib.auth.models import User
from django.db.models import Sum, Count
from django.shortcuts import render
from django.views import View

from api.models import Category, Merchant, Transaction, UserFinancialSummary


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

        Args:
            user: The authenticated user
            selected_year: Optional year filter (YYYY format)
            selected_category: Optional category ID filter

        Returns:
            SummaryPageContext instance ready for template rendering
        """
        # Get all transactions for the user
        transactions = Transaction.objects.filter(user=user, status='categorized').order_by(
            '-transaction_date'
        )

        # Apply filters
        if selected_year:
            transactions = transactions.filter(transaction_date__year=int(selected_year))

        if selected_category:
            transactions = transactions.filter(category_id=int(selected_category))

        # Calculate summary metrics
        total_expenses = transactions.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

        # Calculate average monthly
        monthly_avg = transactions.values('transaction_date__year', 'transaction_date__month').annotate(
            monthly_total=Sum('amount')
        ).aggregate(avg=Sum('monthly_total') / Count('transaction_date__month', distinct=True))['avg'] or Decimal('0')

        # Get top category
        top_category_data = transactions.values('category').annotate(
            total=Sum('amount')
        ).order_by('-total').first()

        top_category = None
        top_category_percentage = 0

        if top_category_data and top_category_data['category']:
            top_category = Category.objects.get(id=top_category_data['category'])
            if total_expenses > 0:
                top_category_percentage = float((top_category_data['total'] / total_expenses) * 100)

        # Get available filters
        available_categories = Category.objects.filter(user=user).order_by('name')
        available_years = sorted(
            set(t.transaction_date.year for t in transactions if t.transaction_date),
            reverse=True
        )

        # Build monthly summaries
        monthly_data = transactions.values('transaction_date__year', 'transaction_date__month').annotate(
            monthly_total=Sum('amount')
        ).order_by('transaction_date__year', 'transaction_date__month')

        monthly_summaries = []
        max_monthly = max((m['monthly_total'] for m in monthly_data), default=Decimal('0'))

        for m in monthly_data:
            year = m['transaction_date__year']
            month = m['transaction_date__month']
            amount = m['monthly_total'] or Decimal('0')

            month_name = date(year, month, 1).strftime('%b')
            percentage = float((amount / max_monthly * 100)) if max_monthly > 0 else 0

            monthly_summaries.append(MonthlySummary(
                month=month_name,
                amount=amount,
                percentage=percentage
            ))

        # Build category breakdowns
        category_breakdowns = []
        category_data = transactions.values('category__id', 'category__name').annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total')

        for cat_data in category_data:
            if cat_data['category__id']:
                category = Category.objects.get(id=cat_data['category__id'])
                cat_percentage = float((cat_data['total'] / total_expenses * 100)) if total_expenses > 0 else 0

                category_breakdowns.append(CategoryBreakdown(
                    category=category,
                    total_amount=cat_data['total'] or Decimal('0'),
                    percentage=cat_percentage,
                    transaction_count=cat_data['count']
                ))

        # Get recent transactions
        recent_transactions = []
        for trans in transactions.select_related('category', 'merchant').order_by('-transaction_date')[:5]:
            recent_transactions.append(RecentTransaction(
                date=trans.transaction_date,
                description=trans.description or "",
                category=trans.category,
                amount=trans.amount or Decimal('0'),
                merchant=trans.merchant
            ))

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