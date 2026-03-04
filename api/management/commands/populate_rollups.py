from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction as db_transaction
from api.services.rollups.rollup_service import RollupService
from api.models import Transaction


class Command(BaseCommand):
    help = 'Populates the YearlyMonthlyUserRollup table for all users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username of a specific user to update (optional)',
        )
        parser.add_argument(
            '--year',
            type=int,
            help='Specific year to update (optional)',
        )

    def handle(self, *args, **options):
        username = options.get('user')
        year_filter = options.get('year')

        # Filter users
        users = User.objects.all()
        if username:
            users = users.filter(username=username)
            if not users.exists():
                self.stdout.write(self.style.ERROR(f'User "{username}" not found'))
                return

        total_users = users.count()
        self.stdout.write(f'Processing {total_users} user(s)...')

        for user_idx, user in enumerate(users, 1):
            self.stdout.write(f'[{user_idx}/{total_users}] Processing user: {user.username}')

            # Get all years with transactions for this user
            years_months = Transaction.objects.filter(user=user).values_list(
                'transaction_date__year',
                'transaction_date__month'
            ).distinct()

            if year_filter:
                years_months = [(y, m) for y, m in years_months if y == year_filter]

            if not years_months:
                self.stdout.write(self.style.WARNING(f'  No transactions found for {user.username}'))
                continue

            # Extract unique years
            years = set(y for y, m in years_months if y is not None)

            self.stdout.write(f'  Found transactions in years: {sorted(years)}')
            self.stdout.write(f'  Updating {len(years_months)} year-month combinations...')

            try:
                with db_transaction.atomic():
                    RollupService.update_all_rollups(user, list(years_months))

                self.stdout.write(self.style.SUCCESS(f'  ✓ Successfully updated rollups for {user.username}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error updating rollups for {user.username}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS('\nRollup population completed!'))