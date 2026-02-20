from django.db import migrations
from api.privacy_utils import encrypt_value, generate_blind_index

def populate_merchant_privacy_fields(apps, schema_editor):
    Merchant = apps.get_model('api', 'Merchant')
    for merchant in Merchant.objects.all():
        if merchant.name:
            merchant.encrypted_name = encrypt_value(merchant.name)
            merchant.name_hash = generate_blind_index(merchant.name)
            merchant.save()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0054_merchant_encrypted_name_merchant_name_hash_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_merchant_privacy_fields, migrations.RunPython.noop),
    ]
