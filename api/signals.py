from allauth.account.signals import user_logged_in
from django.contrib import messages
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import UploadFile, FileStructureMetadata

@receiver(post_save, sender=UploadFile)
def create_file_structure_metadata(sender, instance, created, **kwargs):
    """
    Signal to automatically create FileStructureMetadata
    when an UploadFile entry is updated with structure information.
    """
    # Only proceed if we have the minimum required columns set
    if instance.description_column_name and instance.date_column_name and (
            instance.income_amount_column_name or instance.expense_amount_column_name):

        first_transaction = instance.transactions.first()
        if not first_transaction:
            return

        keys = first_transaction.raw_data.keys()
        row_hash = FileStructureMetadata.generate_tuple_hash(keys)

        # Use get_or_create to avoid duplicates if the same structure
        # is uploaded by different files/users
        FileStructureMetadata.objects.get_or_create(
            row_hash=row_hash,
            defaults={
                'description_column_name': instance.description_column_name,
                'income_amount_column_name': instance.income_amount_column_name,
                'expense_amount_column_name': instance.expense_amount_column_name,
                'date_column_name': instance.date_column_name,
                'merchant_column_name': instance.merchant_column_name,
                'operation_type_column_name': instance.operation_type_column_name,
                'notes': instance.notes,
            }
        )