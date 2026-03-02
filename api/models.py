# models.py
from __future__ import annotations
import hashlib
import re
from typing import Any, Iterable

from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import QuerySet
from django.utils import timezone
from pgvector.django import VectorField, HnswIndex

from api.fields import EncryptedDecimalField, EncryptedCharField
from api.privacy_utils import generate_encrypted_trigrams


class DefaultCategory(models.Model):
    """
    System-level default categories (not tied to any user).

    Intended as a stable catalog you can copy from when a user uploads data
    without having created their own categories.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Default Categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

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

    def __str__(self) -> str:
        return self.name

class Merchant(models.Model):
    """Merchants/vendors where transactions occur"""
    name = EncryptedCharField(db_column='name', blank=True, null=True)
    name_hash = models.CharField(max_length=64, db_index=True, blank=True, null=True)
    address = models.TextField(blank=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='merchants',
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    fuzzy_search_trigrams = ArrayField(models.CharField(blank=True, null=True), blank=True, null=True)

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['user', 'name_hash']),
            GinIndex(fields=['fuzzy_search_trigrams'])
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs: Any) -> None:
        # Update name_hash from the decrypted name
        if self.name:
            from api.privacy_utils import generate_blind_index
            self.name_hash = generate_blind_index(self.name)
        else:
            self.name_hash = None
        encrypted_trigrams = generate_encrypted_trigrams(self.name)
        self.fuzzy_search_trigrams = encrypted_trigrams
        super().save(*args, **kwargs)


class FileStructureMetadata(models.Model):
    description_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV that corresponds to the transaction description."
    )
    income_amount_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV for the transaction amount."
    )
    expense_amount_column_name = models.CharField(
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
    operation_type_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV for the operation type."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    notes = models.TextField(blank=True, help_text='Agent description of the csv structure')

    row_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        # Constraints to ensure uniqueness per user and tuple content
        constraints = [
            models.UniqueConstraint(
                fields=['row_hash'],
                name='unique_user_transaction_row'
            )
        ]

    def save(self, *args, **kwargs: Any) -> None:
        super().save(*args, **kwargs)

    @staticmethod
    def generate_tuple_hash(keys: Iterable[str]) -> str:
        """
        Generates a SHA-256 hash based on the raw CSV keys (headers).
        """
        sorted_keys = sorted(list(keys))
        data_payload = "|".join(sorted_keys)
        return hashlib.sha256(data_payload.encode('utf-8')).hexdigest()


class MerchantEMA(models.Model):
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name='emas'
    )
    file_structure_metadata = models.ForeignKey(
        FileStructureMetadata,
        on_delete=models.SET_NULL,
        related_name='merchant_emas',
        null=True,
    )
    digital_footprint = VectorField(dimensions=384, null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            HnswIndex(
                name='merchant_ema_footprint_hnsw_idx',
                fields=['digital_footprint'],
                opclasses=['vector_cosine_ops']
            )
        ]

    def __str__(self) -> str:
        return f"EMA for {self.merchant.name} (FileStructure: {self.file_structure_metadata.id})"


class UploadFile(models.Model):
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
    income_amount_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV for the transaction amount."
    )
    expense_amount_column_name = models.CharField(
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
    operation_type_column_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The header name in the CSV for the operation type."
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

    file_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The file name"
    )
    notes = models.TextField(blank=True, help_text='Agent description of the csv structure')

    status = models.CharField(max_length=70, choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending')

    file_structure_metadata = models.ForeignKey(
        FileStructureMetadata,
        on_delete=models.SET_NULL,
        related_name='upload_files',
        null=True,
    )




    def __str__(self) -> str:
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



    upload_file = models.ForeignKey(
        UploadFile,
        on_delete=models.CASCADE,
        related_name='transactions',
        null=True,
        blank=True
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
    operation_type = models.CharField(max_length=255, blank=True, null=True)
    # Core transaction data
    transaction_date = models.DateField(null=True, blank=True)
    amount = EncryptedDecimalField(db_column='amount', blank=True, null=True)
    description = EncryptedCharField(db_column='description', blank=True, null=True)
    description_hash = models.CharField(max_length=64, db_index=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    manual_insert = models.BooleanField(default=False)
    # Tracking
    modified_by_user = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    raw_data = models.JSONField(default=dict, null=True)
    categorized_by_agent = models.BooleanField(default=False)
    embedding = VectorField(dimensions=384, null=True, blank=True)

    def save(self, *args, **kwargs: Any) -> None:
        if self.description and not self.description_hash:
            from api.privacy_utils import generate_blind_index
            self.description_hash = generate_blind_index(self.description)
        elif not self.description:
            self.description_hash = None

        super().save(*args, **kwargs)
    class Meta:
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'transaction_type', '-transaction_date', '-created_at']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['user', 'merchant']),
            models.Index(fields=['user', 'description_hash']),
            models.Index(fields=['status']),
            models.Index(fields=['user', 'status']),
            HnswIndex(name='idx_tx_embedding', fields=['embedding'], opclasses=['vector_cosine_ops']),
        ]

    def __str__(self) -> str:
        return f"{self.transaction_date} - {self.merchant or self.description} - €{self.amount}"

    @classmethod
    def find_similar_by_embedding(cls, user: User, embedding: list[float], limit: int = 5) -> QuerySet[Transaction]:
        from pgvector.django import CosineDistance
        return cls.objects.filter(
            user=user,
            embedding__isnull=False,
            category__isnull=False
        ).annotate(
            distance=CosineDistance('embedding', embedding)
        ).order_by('distance')[:limit]


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

class OnboardingStep(models.Model):
    step_number = models.IntegerField(unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    mock_type = models.CharField(max_length=100)

    class Meta:
        ordering = ['step_number']

    def __str__(self) -> str:
        return f"Step {self.step_number}: {self.title}"

class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    subscription_type = models.CharField(max_length=50, default='free_trial')
    onboarding_step = models.IntegerField(default=1, help_text="1: Categories, 2: Upload, 3: Filters, 4: Personalize, 5: Completed")
    welcome_email_sent = models.BooleanField(default=False)
    needs_rollup_recomputation = models.BooleanField(default=True)
    def __str__(self) -> str:
        return f"{self.user.username}'s profile"


class YearlyMonthlyUserRollup(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='yearly_rollups')
    by_year = models.IntegerField()
    total_amount_expense_by_year = EncryptedDecimalField(blank=True, null=True)
    total_amount_income_by_year = EncryptedDecimalField(blank=True, null=True)
    total_amount_expense_by_month = EncryptedDecimalField(blank=True, null=True)
    total_amount_income_by_month = EncryptedDecimalField(blank=True, null=True)
    month_number = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'by_year', 'month_number')
        verbose_name = "Yearly Monthly User Rollup"
        verbose_name_plural = "Yearly Monthly User Rollups"

    def __str__(self) -> str:
        return f"{self.user.username} - {self.by_year} - {self.month_number}"


class MonthlyBudget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey('Category', on_delete=models.CASCADE)

    # The month this budget refers to (e.g., 2026-03-01)
    month = models.DateField()

    # The actual budget goal
    # formula: trend.suggested_unit_amount * trend.estimated_monthly_frequency
    planned_amount = EncryptedDecimalField(default=0)

    user_amount = EncryptedDecimalField(default=None, null=True, blank=True)

    # Track if the user manually changed the AI suggestion
    is_automated = models.BooleanField(default=True)

    # To store historical snapshots if needed (optional)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def final_amount(self)->float:
        if self.is_automated:
            return float(self.planned_amount or 0.0)
        return float(self.user_amount if self.user_amount is not None else self.planned_amount)


    class Meta:
        unique_together = ('user', 'category', 'month')


class CategoryRollup(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='category_rollups')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='rollups')
    year = models.IntegerField()
    month_number = models.IntegerField(blank=True, null=True)
    total_spent = EncryptedDecimalField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'category', 'year', 'month_number')
        verbose_name = "Category Rollup"
        verbose_name_plural = "Category Rollups"

    def __str__(self) -> str:
        return f"{self.user.username} - {self.category.name} - {self.year}/{self.month_number or 'YEAR'}"
