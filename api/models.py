# models.py
import re

from django.contrib.auth.models import User
from django.contrib.postgres.lookups import TrigramWordSimilar
from django.contrib.postgres.search import TrigramSimilarity, TrigramWordSimilarity
from django.db import models
from django.db.models import QuerySet, Q
from django.db.models.expressions import RawSQL


class Category(models.Model):
    """Expense categories (user-defined or default)"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)  # System vs user-created
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='categories'
    )  # Null = default/system category
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
        unique_together = [['name', 'user']]  # Unique per user

    def __str__(self):
        return self.name


class Merchant(models.Model):
    """Merchants/vendors where transactions occur"""
    name = models.CharField(max_length=255)  # Normalized name
    normalized_name = models.CharField(max_length=255, db_index=True)  # For fuzzy matching
    description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='merchants'
    )
    default_categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name='default_merchants'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @staticmethod
    def get_merchants_by_transaction_description(description: str, user: User) -> QuerySet:
        return Merchant.objects.annotate(
            input_contains_normalized=RawSQL(
                "%s ILIKE '%%' || normalized_name || '%%'",
                (normalize_string(description),)
            ),
            normalized_contains_input=RawSQL(
                "normalized_name ILIKE '%%' || %s || '%%'",
                (normalize_string(description),)
            )
        ).filter(
            Q(input_contains_normalized=True) |
            Q(normalized_contains_input=True)
        ).filter(
            user=user
        ).distinct('normalized_name').order_by('normalized_name')

    @staticmethod
    def get_similar_merchants_by_names(merchant_name_candidate: str, user: User,
                                       similarity_threshold: float) -> QuerySet:

        return Merchant.objects.filter(user=user, normalized_name__exact=normalize_string(
            merchant_name_candidate)) or Merchant.objects.annotate(
            similarity=TrigramWordSimilarity(normalize_string(merchant_name_candidate),'normalized_name')
        ).filter(
            similarity__gte=similarity_threshold,
            user=user
        ).order_by('-similarity')

    def save(self, *args, **kwargs):
        # Auto-normalize name for fuzzy matching
        self.normalized_name = normalize_string(self.name)
        super().save(*args, **kwargs)


class CsvUpload(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='csv_maps',
    )

    description_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV that corresponds to the transaction description."
    )
    amount_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV for the transaction amount."
    )
    date_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV for the transaction date."
    )
    merchant_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV for the merchant or payee name."
    )

    upload_date = models.DateTimeField(
        auto_now_add=True,
        help_text="The date and time the mapping record was created/uploaded."
    )
    dimension = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="The size of the associated CSV file in bytes."
    )
    processing_time = models.IntegerField(
        null=True,
        blank=True,
        help_text="The time taken to process the associated CSV file (in milliseconds)."
    )

    def __str__(self):
        return f"CSV Map (Upload: {self.upload_date.strftime('%Y-%m-%d')})"


class Transaction(models.Model):
    """Individual financial transactions"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('categorized', 'Categorized'),
        ('reviewed', 'Reviewed'),
    ]
    TRANSACTION_TYPE_CHOICES = [
        ('expense', 'Expense'),
        ('income', 'Income'),
    ]



    csv_upload = models.ForeignKey(
        CsvUpload,
        on_delete=models.CASCADE,
        related_name='transactions',
        null=False
    )
    # Relationships
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES, default='expense')
    # Processing metadata
    merchant_raw_name = models.CharField(max_length=255, blank=True)  # Original from CSV
    # Core transaction data
    transaction_date = models.DateField(null=True)
    original_date = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    original_amount = models.CharField(max_length=50, blank=True, null=True)  # Raw from CSV
    description = models.TextField(null=True)  # Raw description from bank
    normalized_description = models.TextField(null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    confidence_score = models.FloatField(null=True, blank=True)  # LLM/matching confidence
    failure_code = models.CharField(max_length=20, null=True, blank=True)
    # Tracking
    modified_by_user = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    raw_data = models.JSONField(default=dict)
    categorized_by_agent = models.BooleanField(default=False)


    def save(self, *args, **kwargs):
        # Auto-normalize name for fuzzy matching
        self.normalized_description = normalize_string(self.description)
        super().save(*args, **kwargs)
    class Meta:
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'transaction_date']),
            models.Index(fields=['merchant', 'category']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.transaction_date} - {self.merchant_raw_name or self.merchant} - €{self.amount}"


class Rule(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='rules'
    )
    text_content = models.TextField(
        verbose_name='Rule Text'  # Uses TextField for more flexible content
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rules'
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.SET_NULL,
        null=True,
    )


    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

class UserFinancialSummary(models.Model):
    """
    Database view that provides a financial summary for each user.
    Shows total spending, monthly average, and top spending category.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.DO_NOTHING,
        related_name='financial_summary',
        primary_key=True
    )
    total_spending = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Total amount spent across all categorized expenses"
    )
    monthly_average_spending = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Average spending per active month"
    )
    top_category_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID of the category with highest spending"
    )
    top_category_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Name of the top spending category"
    )
    top_category_spending = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Top category total expenses amount"
    )
    top_category_percentage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Percentage of total spending for top category"
    )
    class Meta:
        managed = False  # This is a database view, not a regular table
        db_table = 'user_financial_summary'
        verbose_name = "User Financial Summary"
        verbose_name_plural = "User Financial Summaries"

    def __str__(self):
        return f"Financial Summary - {self.user.username}"

def normalize_string(input_data:str)->str:
    return re.sub(r'[^a-z0-9]', '', input_data.lower())