from django.db import migrations
from pgvector.django import VectorExtension

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0035_alter_profile_onboarding_step'),
    ]

    operations = [
        VectorExtension(),
    ]
