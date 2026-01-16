from django.core.management.base import BaseCommand
from api.models import CsvUpload, Rule, Category
from processors.expense_upload_processor import ExpenseUploadProcessor

class Command(BaseCommand):
    help = 'Resumes CSV uploads that were interrupted by a server shutdown'

    def handle(self, *args, **options):
        # Find uploads that never finished
        incomplete_uploads = CsvUpload.objects.filter(status='processing')
        
        if not incomplete_uploads.exists():
            self.stdout.write("No interrupted uploads found.")
            return

        for upload in incomplete_uploads:
            self.stdout.write(f"Resuming Upload ID: {upload.id} for user {upload.user}")
            
            # Fetch the transactions tied to this upload that are still pending
            pending_txs = list(upload.transactions.filter(status='pending'))
            
            if pending_txs:
                # Fetch user rules and categories
                user_rules = list(
                    Rule.objects.filter(
                        user=upload.user,
                        is_active=True
                    ).values_list('text_content', flat=True)
                )
                available_categories = list(Category.objects.filter(user=upload.user))
                
                # Re-initialize the processor
                processor = ExpenseUploadProcessor(
                    user=upload.user,
                    user_rules=user_rules,
                    available_categories=available_categories
                )
                processor.process_transactions(pending_txs, upload)

                self.stdout.write(self.style.SUCCESS(f"Successfully resumed Upload {upload.id}"))
            else:
                upload.status = 'completed'
                upload.save()
                self.stdout.write(f"Upload {upload.id} was already finished (no pending transactions).")
