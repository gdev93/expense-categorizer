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
                    SELECT MIN(transaction_date) AS start_date,
                           MAX(transaction_date) AS end_date
                    FROM api_transaction),
                     all_month_years AS (
                         -- 2. Generate a list of all distinct month-year combinations in the range
                         SELECT DATE_TRUNC('month',
                                           generate_series(start_date, end_date, '1 month'::interval))         AS monthly_date,
                                EXTRACT(YEAR FROM generate_series(start_date, end_date, '1 month'::interval))  AS year,
                                EXTRACT(MONTH FROM generate_series(start_date, end_date, '1 month'::interval)) AS month
                         FROM date_range),
                     base_combinations AS (
                         -- 3. FIX: Join users only with categories they own or default categories (user_id IS NULL)
                         SELECT u.user_id,
                                c.id   AS category_id,
                                c.name AS category_name,
                                amy.year,
                                amy.month
                         FROM (
                                  -- Select all distinct users who have transactions
                                  SELECT DISTINCT user_id
                                  FROM api_transaction) u
                                  -- INNER JOIN ensures we only create combinations for relevant users and their categories
                                  INNER JOIN api_category c
                                             ON c.user_id = u.user_id OR c.user_id IS NULL

                                  CROSS JOIN all_month_years amy)
                SELECT bc.user_id,
                       bc.category_id,
                       bc.category_name,
                       COALESCE(SUM(t.amount), 0) AS total_amount, -- Use COALESCE to default to 0
                       bc.year,
                       bc.month
                FROM base_combinations bc
-- 5. LEFT JOIN the original transaction data to this refined comprehensive list
                         LEFT JOIN api_transaction t ON
                    t.user_id = bc.user_id AND
                    t.category_id = bc.category_id AND
                    EXTRACT(YEAR FROM t.transaction_date) = bc.year AND
                    EXTRACT(MONTH FROM t.transaction_date) = bc.month
                WHERE
                   -- Filter transactions based on the original criteria (status and type)
                    (t.status = 'categorized' AND t.transaction_type = 'expense')
                   OR t.transaction_date IS NULL
                GROUP BY bc.user_id,
                         bc.category_id,
                         bc.category_name,
                         bc.year,
                         bc.month
                ORDER BY bc.user_id,
                         bc.year DESC,
                         bc.month DESC,
                         bc.category_name;
                """,
            reverse_sql="DROP VIEW IF EXISTS category_monthly_summary;",
        ),
    ]