# models.py
from django.contrib.auth.models import User
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
    def get_similar_merchants_by_names(compare: str, user: User, similarity_threshold: float) -> QuerySet:
        """
        Find merchants similar to the compare string using:
        1. Substring containment (ILIKE)
        2. Word similarity (PostgreSQL trigram)

        Args:
            compare: The merchant name to search for
            user: The user whose merchants to search
            similarity_threshold: Minimum similarity score (0.0 to 1.0)

        Returns:
            QuerySet of matching Merchant objects ordered by similarity
        """

        return Merchant.objects.annotate(
            is_contained_name=RawSQL(
                "%s ILIKE '%%' || name || '%%'",
                (compare,)
            ),
            is_contained_normalized_name=RawSQL(
                "%s ILIKE '%%' || normalized_name || '%%'",
                (compare,)
            ),
            name_similarity=RawSQL(
                "word_similarity(name, %s)",
                (compare,)
            ),
            normalized_name_similarity=RawSQL(
                "word_similarity(normalized_name, %s)",
                (compare,)
            )
        ).filter(
            Q(is_contained_name=True) |
            Q(is_contained_normalized_name=True) |
            Q(name__icontains=compare) |
            Q(normalized_name__icontains=compare) |
            Q(name_similarity__gte=similarity_threshold) |
            Q(normalized_name_similarity__gte=similarity_threshold)
        ).filter(
            user=user
        ).order_by(
            '-name_similarity',
            '-normalized_name_similarity'
        ).distinct()

    def save(self, *args, **kwargs):
        # Auto-normalize name for fuzzy matching
        self.normalized_name = self.name.upper().strip().replace("  ", " ")
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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    confidence_score = models.FloatField(null=True, blank=True)  # LLM/matching confidence
    failure_code = models.CharField(max_length=20, null=True, blank=True)
    # Tracking
    modified_by_user = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    raw_data = models.JSONField(default=dict)

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

