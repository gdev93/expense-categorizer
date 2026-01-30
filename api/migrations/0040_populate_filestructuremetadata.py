import hashlib
from django.db import migrations

def generate_tuple_hash(keys):
    """
    Generates a SHA-256 hash based on the raw CSV keys (headers).
    """
    sorted_keys = sorted(list(keys))
    data_payload = "|".join(sorted_keys)
    return hashlib.sha256(data_payload.encode('utf-8')).hexdigest()

def populate_metadata(apps, schema_editor):
    UploadFile = apps.get_model('api', 'UploadFile')
    FileStructureMetadata = apps.get_model('api', 'FileStructureMetadata')
    Transaction = apps.get_model('api', 'Transaction')

    for upload_file in UploadFile.objects.all():
        # Check if we have the minimum required columns set
        if upload_file.description_column_name and upload_file.date_column_name and (
                upload_file.income_amount_column_name or upload_file.expense_amount_column_name):

            # Use .filter().first() to avoid exceptions if no transactions exist
            first_transaction = Transaction.objects.filter(upload_file=upload_file).first()
            if not first_transaction or not first_transaction.raw_data:
                continue

            keys = first_transaction.raw_data.keys()
            if not keys:
                continue
                
            row_hash = generate_tuple_hash(keys)

            # Use get_or_create to avoid duplicates if multiple files have the same structure
            FileStructureMetadata.objects.get_or_create(
                row_hash=row_hash,
                defaults={
                    'description_column_name': upload_file.description_column_name,
                    'income_amount_column_name': upload_file.income_amount_column_name,
                    'expense_amount_column_name': upload_file.expense_amount_column_name,
                    'date_column_name': upload_file.date_column_name,
                    'merchant_column_name': upload_file.merchant_column_name,
                    'operation_type_column_name': upload_file.operation_type_column_name,
                    'notes': upload_file.notes or '',
                }
            )

def reverse_populate_metadata(apps, schema_editor):
    FileStructureMetadata = apps.get_model('api', 'FileStructureMetadata')
    FileStructureMetadata.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0039_filestructuremetadata'),
    ]

    operations = [
        migrations.RunPython(populate_metadata, reverse_populate_metadata),
    ]
