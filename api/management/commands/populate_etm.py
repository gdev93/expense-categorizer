from django.core.management.base import BaseCommand

from api.models import Merchant


class Command(BaseCommand):
    help = 'Populates the Merchant fuzzy search columns for all users'

    def handle(self, *args, **options):
        for merchant in Merchant.objects.all():
            # trigger re-encryption
            merchant.save()
