# migrations/0XXX_create_user_financial_summary_view.py
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_monthly_summary_stats'),  # Replace with your actual last migration
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE VIEW category_monthly_summary AS
                WITH date_range AS (
                    -- 1. Define the overall date range
                    SELECT 
                        MIN(transaction_date) AS start_date,
                        MAX(transaction_date) AS end_date
                    FROM api_transaction
                ),
                all_month_years AS (
                    -- 2. Generate a list of all distinct month-year combinations in the range
                    SELECT 
                        DATE_TRUNC('month', generate_series(start_date, end_date, '1 month'::interval)) AS monthly_date,
                        EXTRACT(YEAR FROM generate_series(start_date, end_date, '1 month'::interval)) AS year,
                        EXTRACT(MONTH FROM generate_series(start_date, end_date, '1 month'::interval)) AS month
                    FROM date_range
                ),
                base_combinations AS (
                    -- 3. Create a Cartesian product of users, categories, and all month/year periods
                    SELECT 
                        u.user_id,
                        c.id AS category_id,
                        c.name AS category_name,
                        amy.year,
                        amy.month
                    FROM (
                        SELECT DISTINCT user_id FROM api_transaction
                    ) u
                    CROSS JOIN api_category c
                    CROSS JOIN all_month_years amy
                )
                SELECT
                    bc.user_id,
                    bc.category_id,
                    bc.category_name,
                    COALESCE(SUM(t.amount), 0) AS total_amount, -- 4. Use COALESCE to default to 0
                    bc.year,
                    bc.month
                FROM
                    base_combinations bc
                -- 5. LEFT JOIN the original transaction data to this comprehensive list
                LEFT JOIN api_transaction t ON 
                    t.user_id = bc.user_id AND
                    t.category_id = bc.category_id AND
                    EXTRACT(YEAR FROM t.transaction_date) = bc.year AND
                    EXTRACT(MONTH FROM t.transaction_date) = bc.month
                WHERE 
                    -- Filter transactions based on the original criteria (status and type)
                    (t.status = 'categorized' AND t.transaction_type = 'expense') OR t.transaction_date IS NULL 
                GROUP BY
                    bc.user_id,
                    bc.category_id,
                    bc.category_name,
                    bc.year,
                    bc.month
                ORDER BY
                    bc.user_id,
                    bc.year DESC, -- Sort by year descending
                    bc.month DESC, -- Sort by month descending
                    bc.category_name;
                """,
            reverse_sql="DROP VIEW IF EXISTS category_monthly_summary;",
        ),
    ]