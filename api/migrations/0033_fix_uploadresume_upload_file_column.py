from django.db import migrations, connection

def rename_column_if_exists(apps, schema_editor):
    with connection.cursor() as cursor:
        # Check if api_uploadresume table has csv_upload_id column
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'api_uploadresume' AND column_name = 'csv_upload_id'
        """)
        if cursor.fetchone():
            print("Renaming csv_upload_id to upload_file_id in api_uploadresume table...")
            cursor.execute("ALTER TABLE api_uploadresume RENAME COLUMN csv_upload_id TO upload_file_id")

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0032_fix_transaction_upload_file_column'),
    ]

    operations = [
        migrations.RunPython(rename_column_if_exists, migrations.RunPython.noop),
    ]
