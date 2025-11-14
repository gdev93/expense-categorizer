# migrations/0XXX_create_user_financial_summary_view.py
from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),  # Replace with your actual last migration
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE VIEW user_financial_summary AS
                WITH userExpenses AS (SELECT t.user_id,
                                             t.amount,
                                             t.transaction_date,
                                             c.id   AS category_id,
                                             c.name AS category_name
                                      FROM api_transaction t
                                               JOIN api_category c ON t.category_id = c.id
                                      WHERE t.transaction_type = 'expense'
                                        AND t.status = 'categorized'),
                     userAggregates AS (SELECT ue.user_id,
                                               COALESCE(SUM(ue.amount), 0.00)                           AS total_spending,
                                               COUNT(DISTINCT DATE_TRUNC('month', ue.transaction_date)) AS num_active_months
                                        FROM userExpenses ue
                                        GROUP BY ue.user_id),
                     categoryRanking AS (SELECT user_id,
                                                category_id,
                                                MIN(category_name)                                                 AS category_name,
                                                SUM(amount)                                                        AS category_total,
                                                ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY SUM(amount) DESC) as rn
                                         FROM userExpenses
                                         GROUP BY user_id, category_id)
                SELECT ua.user_id,
                       ua.total_spending,
                       CASE
                           WHEN ua.num_active_months > 0
                               THEN ROUND(ua.total_spending / ua.num_active_months, 2)
                           ELSE 0.00
                           END           AS monthly_average_spending,
                       cr.category_id    AS top_category_id,
                       cr.category_name  AS top_category_name,
                       cr.category_total AS top_category_spending,
                       CASE
                           WHEN ua.total_spending > 0
                               THEN ROUND((cr.category_total / ua.total_spending) * 100, 2)
                           ELSE 0.00
                           END           AS top_category_percentage
                FROM userAggregates ua
                         LEFT JOIN
                     categoryRanking cr ON ua.user_id = cr.user_id AND cr.rn = 1;
                """,
            reverse_sql="DROP VIEW IF EXISTS user_financial_summary;",
        ),
    ]