from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_remove_internalbanktransfer_expense_date_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP VIEW IF EXISTS internal_bank_transfer;",
            reverse_sql="""
            CREATE OR REPLACE VIEW internal_bank_transfer AS
            SELECT DISTINCT ON (ti.id)
                te.user_id,
                te.id AS expense_id,
                ti.id AS income_id,
                te.amount,
                te.description AS expense_desc,
                ti.description AS income_desc,
                te.transaction_date AS expense_date,
                ti.transaction_date AS income_date,
                (
                    -- SCORING LOGIC
                    CASE 
                        WHEN te.transaction_date = ti.transaction_date THEN 40
                        WHEN ABS(te.transaction_date - ti.transaction_date) <= 1 THEN 30
                        ELSE 10
                    END +
                    CASE 
                        WHEN te.normalized_description = ti.normalized_description THEN 60
                        WHEN (te.description ILIKE '%%' || ti.description || '%%' OR 
                              ti.description ILIKE '%%' || te.description || '%%') THEN 40
                        ELSE 0
                    END
                ) AS raw_score
            FROM api_transaction te
            JOIN api_transaction ti ON 
                te.user_id = ti.user_id 
                AND te.amount = ti.amount
            WHERE 
                te.transaction_type = 'expense' 
                AND ti.transaction_type = 'income'
                AND ti.id != te.id
                -- Bidirectional 4-day window
                AND ti.transaction_date BETWEEN te.transaction_date - INTERVAL '4 days' 
                                            AND te.transaction_date + INTERVAL '4 days'
            ORDER BY ti.id, raw_score DESC, te.transaction_date ASC;
            """
        ),
    ]
