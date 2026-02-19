# models.py
import hashlib
import re

from django.contrib.auth.models import User
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL
from pgvector.django import VectorField, HnswIndex
from api.privacy_utils import encrypt_value, decrypt_value, generate_blind_index


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

    def __str__(self):
        return self.name


class Merchant(models.Model):
    """Merchants/vendors where transactions occur"""
    encrypted_name = models.TextField(blank=True, null=True)
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

    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['user', 'name_hash']),
        ]

    @property
    def name(self):
        if not hasattr(self, '_decrypted_name'):
            from api.privacy_utils import decrypt_value
            self._decrypted_name = decrypt_value(self.encrypted_name) or ""
        return self._decrypted_name

    @name.setter
    def name(self, value):
        from api.privacy_utils import encrypt_value, generate_blind_index
        self._decrypted_name = value
        if value:
            self.encrypted_name = encrypt_value(value)
            self.name_hash = generate_blind_index(value)
        else:
            self.encrypted_name = None
            self.name_hash = None

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Privacy by Design logic is now handled in the name setter if used,
        # but we also ensure fields are set here if 'name' was set as an attribute
        if hasattr(self, '_decrypted_name') and self._decrypted_name:
            from api.privacy_utils import encrypt_value, generate_blind_index
            self.encrypted_name = encrypt_value(self._decrypted_name)
            self.name_hash = generate_blind_index(self._decrypted_name)
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @staticmethod
    def generate_tuple_hash(keys):
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

    def __str__(self):
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
    encrypted_amount = models.TextField(blank=True, null=True)
    encrypted_description = models.TextField(blank=True, null=True)
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

    @property
    def amount(self):
        if not hasattr(self, '_decrypted_amount'):
            from api.privacy_utils import decrypt_value
            from decimal import Decimal
            val = decrypt_value(self.encrypted_amount)
            try:
                self._decrypted_amount = Decimal(val) if val is not None else None
            except Exception:
                self._decrypted_amount = None
        return self._decrypted_amount

    @amount.setter
    def amount(self, value):
        from api.privacy_utils import encrypt_value
        self._decrypted_amount = value
        if value is not None:
            self.encrypted_amount = encrypt_value(value)
        else:
            self.encrypted_amount = None

    @property
    def description(self):
        if not hasattr(self, '_decrypted_description'):
            from api.privacy_utils import decrypt_value
            self._decrypted_description = decrypt_value(self.encrypted_description) or ""
        return self._decrypted_description

    @description.setter
    def description(self, value):
        from api.privacy_utils import encrypt_value, generate_blind_index
        self._decrypted_description = value
        if value:
            self.encrypted_description = encrypt_value(value)
            self.description_hash = generate_blind_index(value)
        else:
            self.encrypted_description = None
            self.description_hash = None

    def save(self, *args, **kwargs):
        # Privacy by Design: Encrypted fields are updated via properties setters
        # but we ensure they are consistent if attributes were set directly
        from api.privacy_utils import encrypt_value, generate_blind_index
        if hasattr(self, '_decrypted_amount') and self._decrypted_amount is not None:
            self.encrypted_amount = encrypt_value(self._decrypted_amount)
        
        if hasattr(self, '_decrypted_description') and self._decrypted_description:
            self.encrypted_description = encrypt_value(self._decrypted_description)
            self.description_hash = generate_blind_index(self._decrypted_description)

        # AGGREGATION STRATEGY: SQL-level SUM() or AVG() on the amount field will no longer work
        # because the data is encrypted. Strategy: Use Django Signals to update a summary table
        # (e.g. UserFinancialSummary or MonthlySummary) with non-encrypted aggregates,
        # or perform calculations in-memory by decrypting values on the fly.

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

    def __str__(self):
        return f"{self.transaction_date} - {self.merchant or self.description} - €{self.amount}"

    @classmethod
    def find_similar_by_embedding(cls, user, embedding, limit=5):
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

    def __str__(self):
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
    def __str__(self):
        return f"{self.user.username}'s profile"

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


class MonthlySummary(models.Model):
    # This field links to the primary table's user, assuming a Foreign Key relationship
    # If the view doesn't enforce a FK, use IntegerField or CharField as appropriate.
    user_id = models.IntegerField(primary_key=True)

    # The aggregated amount
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # The month number (1-12)
    month = models.SmallIntegerField()

    year = models.SmallIntegerField()

    # The type of transaction (e.g., 'income', 'expense')
    transaction_type = models.CharField(max_length=50)

    class Meta:
        # 1. IMPORTANT: Set managed = False to tell Django NOT to create/manage this
        #    'table' (which is actually your view) in the database.
        managed = False

        # 2. Specify the exact name of your database view.
        db_table = 'monthly_financial_summary'

        # 3. Define a unique combination of fields that makes a row distinct.
        #    This is essential because Django expects a primary key.
        #    The combination of user_id, month, and transaction_type is unique in your view.
        unique_together = ('user_id', 'month', 'transaction_type')

        # 4. (Optional) Define a verbose name for the Admin interface.
        verbose_name = 'Monthly Financial Summary'

    def __str__(self):
        return f"{self.user_id} - {self.transaction_type} ({self.month}): {self.total_amount}"


class CategoryMonthlySummary(models.Model):
    pk = models.CompositePrimaryKey("user_id", "category_id", "year", "month")
    # Foreign key field from the api_transaction table
    user_id = models.IntegerField()

    # Fields from the api_category table
    category_id = models.IntegerField()
    category_name = models.CharField(max_length=100)

    # The aggregated amount (COALESCE(SUM(t.amount), 0))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # The time period fields
    year = models.SmallIntegerField()
    month = models.SmallIntegerField()

    class Meta:
        # 1. IMPORTANT: This tells Django not to manage the table/view schema.
        #    The view must be created manually in the database.
        managed = False

        # 2. Set the exact name of the database view this model maps to.
        #    (Assuming you named the view 'zero_filled_monthly_summary')
        db_table = 'category_monthly_summary'

        # 3. Define the combination of fields that makes each row unique in the view.
        #    Django requires a primary key or a unique constraint.
        unique_together = ('user_id', 'category_id', 'year', 'month')

        # 4. (Optional) Define a verbose name for clarity.
        verbose_name = 'Zero-Filled Monthly Summary'

    def __str__(self):
        return f"User {self.user_id} - {self.category_name} ({self.year}-{self.month}): {self.total_amount}"


def normalize_string(input_data:str)->str:
    if not input_data:
        return ''
    return re.sub(r'[^a-z0-9]', '', input_data.lower())