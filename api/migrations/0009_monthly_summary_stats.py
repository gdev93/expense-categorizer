# migrations/0XXX_create_user_financial_summary_view.py
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_csvupload_file_name'),  # Replace with your actual last migration
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE VIEW monthly_financial_summary AS
                SELECT
                    user_id,
                    SUM(amount) AS total_amount,
                    EXTRACT(YEAR FROM transaction_date) AS year, -- 1. Added YEAR extraction
                    EXTRACT(MONTH FROM transaction_date) AS month,
                    transaction_type
                FROM
                    api_transaction
                WHERE status = 'categorized'
                GROUP BY
                    user_id,
                    year, -- 2. Added 'year' to the grouping
                    month,
                    transaction_type
                ORDER BY
                    user_id,
                    year,
                    month;
                """,
            reverse_sql="DROP VIEW IF EXISTS monthly_financial_summary;",
        ),
    ]