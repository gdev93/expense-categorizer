# models.py
import re

from django.contrib.auth.models import User
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import TrigramWordSimilarity
from django.db import models
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL


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
    name = models.CharField(max_length=255)  # Normalized name
    normalized_name = models.CharField(max_length=255, db_index=True)  # For fuzzy matching
    description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='merchants'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['user', 'name']),
            models.Index(fields=['user', 'normalized_name']),
            GinIndex(fields=['name'], name='merchant_name_trgm_idx', opclasses=['gin_trgm_ops']),
            GinIndex(fields=['normalized_name'], name='merchant_norm_name_trgm_idx', opclasses=['gin_trgm_ops']),
        ]

    def __str__(self):
        return self.name

    @staticmethod
    def get_merchants_by_transaction_description(description: str, user: User, threshold:float) -> QuerySet:
        """
        Finds merchants where the merchant name is highly similar to words
        found in the description.
        """
        # TrigramWordSimilarity splits the description into words and compares
        # them against the merchant name.
        return Merchant.objects.annotate(
            similarity=RawSQL(sql="WORD_SIMILARITY(name, %s)", params=(description,))
        ).filter(
            user=user,
            similarity__gte=threshold  # Adjust threshold (0.6 is usually a strong match)
        ).order_by('-similarity')

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
    operation_type = models.CharField(max_length=255, blank=True, null=True)
    # Processing metadata
    merchant_raw_name = models.CharField(max_length=255, blank=True, null=True)  # Original from CSV
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
    reasoning = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        # Auto-normalize name for fuzzy matching
        self.normalized_description = normalize_string(self.description)
        super().save(*args, **kwargs)
    class Meta:
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['user', 'transaction_type', '-transaction_date', '-created_at']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['user', 'merchant']),
            models.Index(fields=['user', 'amount']),
            models.Index(fields=['status']),
            models.Index(fields=['user', 'status']),
            GinIndex(fields=['merchant_raw_name'], name='trans_merch_raw_trgm_idx', opclasses=['gin_trgm_ops']),
            GinIndex(fields=['description'], name='trans_desc_trgm_idx', opclasses=['gin_trgm_ops']),
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

class InternalBankTransfer(models.Model):
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING,
                             related_name='internal_transfers',
                             db_column='user_id')

    income_transaction = models.OneToOneField(
        'Transaction',
        on_delete=models.DO_NOTHING,
        db_column='income_id',
        primary_key=True,
        related_name='internal_transfer_in'
    )

    # The best matching expense found by the scoring logic
    expense_transaction = models.ForeignKey(
        'Transaction',
        on_delete=models.DO_NOTHING,
        db_column='expense_id',
        related_name='internal_transfer_out'
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Keep track of the dates for easy UI sorting
    expense_date = models.DateField()
    income_date = models.DateField()

    class Meta:
        verbose_name = "Internal Bank Transfer"
        verbose_name_plural = "Internal Bank Transfers"

    def __str__(self):
        return f"Transfer Match: {self.amount}"

def normalize_string(input_data:str)->str:
    if not input_data:
        return ''
    return re.sub(r'[^a-z0-9]', '', input_data.lower())