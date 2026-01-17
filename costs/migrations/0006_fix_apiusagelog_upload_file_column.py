from django.db import migrations, connection

def rename_column_if_exists(apps, schema_editor):
    with connection.cursor() as cursor:
        # Check if costs_apiusagelog table has csv_upload_id column
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'costs_apiusagelog' AND column_name = 'csv_upload_id'
        """)
        if cursor.fetchone():
            print("Renaming csv_upload_id to upload_file_id in costs_apiusagelog table...")
            cursor.execute("ALTER TABLE costs_apiusagelog RENAME COLUMN csv_upload_id TO upload_file_id")

class Migration(migrations.Migration):

    dependencies = [
        ('costs', '0005_apiusagelog_final_earning_apiusagelog_input_cost_and_more'),
    ]

    operations = [
        migrations.RunPython(rename_column_if_exists, migrations.RunPython.noop),
    ]
