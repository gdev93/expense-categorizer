from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0018_internal_bank_transfer'),
    ]

    operations = [
        # Drop the view first
        migrations.RunSQL(
            sql="DROP VIEW IF EXISTS internal_bank_transfer CASCADE;",
            reverse_sql="-- View recreated below"
        ),

        # Now create it fresh
        migrations.RunSQL(
            sql="""
                CREATE VIEW internal_bank_transfer AS
                WITH numbered_expenses AS (SELECT *,
                                                  ROW_NUMBER() OVER (
                                                      PARTITION BY user_id, amount, transaction_date
                                                      ORDER BY id
                                                      ) as occurrence_link
                                           FROM api_transaction
                                           WHERE transaction_type = 'expense'),
                     numbered_incomes AS (SELECT *,
                                                 ROW_NUMBER() OVER (
                                                     PARTITION BY user_id, amount, transaction_date
                                                     ORDER BY id
                                                     ) as occurrence_link
                                          FROM api_transaction
                                          WHERE transaction_type = 'income')
                SELECT te.user_id,
                       te.id               AS expense_id,
                       ti.id               AS income_id,
                       te.amount,
                       te.description      AS expense_desc,
                       ti.description      AS income_desc,
                       te.transaction_date AS expense_date,
                       ti.transaction_date AS income_date
                FROM numbered_expenses te
                         JOIN numbered_incomes ti ON
                    te.user_id = ti.user_id
                        AND te.amount = ti.amount
                        AND te.occurrence_link = ti.occurrence_link
                WHERE te.id != ti.id
                  AND ti.transaction_date BETWEEN te.transaction_date - INTERVAL '4 days'
                    AND te.transaction_date + INTERVAL '4 days';
                """,
            reverse_sql="DROP VIEW IF EXISTS internal_bank_transfer CASCADE;"
        ),
    ]