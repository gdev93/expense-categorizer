# models.py
from django.db import models
from django.contrib.auth.models import User


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

    def save(self, *args, **kwargs):
        # Auto-normalize name for fuzzy matching
        self.normalized_name = self.name.upper().strip().replace("  ", " ")
        super().save(*args, **kwargs)


class Transaction(models.Model):
    """Individual financial transactions"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('categorized', 'Categorized'),
        ('reviewed', 'Reviewed'),
    ]

    # Core transaction data
    transaction_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    original_amount = models.CharField(max_length=50, blank=True)  # Raw from CSV
    description = models.TextField()  # Raw description from bank

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

    # Processing metadata
    merchant_raw_name = models.CharField(max_length=255, blank=True)  # Original from CSV
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    confidence_score = models.FloatField(null=True, blank=True)  # LLM/matching confidence

    # Tracking
    modified_by_user = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    """Keyword-based categorization rules"""
    RULE_TYPES = [
        ('keyword', 'Keyword Match'),
        ('merchant', 'Merchant Match'),
        ('amount', 'Amount Match'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='rules'
    )
    rule_type = models.CharField(max_length=20, choices=RULE_TYPES, default='keyword')
    keyword = models.CharField(max_length=255)  # What to match
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='rules'
    )
    priority = models.IntegerField(default=0)  # Higher = applied first
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"{self.keyword} → {self.category.name}"