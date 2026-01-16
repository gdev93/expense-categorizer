from django.core.management.base import BaseCommand
from django.db import IntegrityError
from api.models import CsvUpload, Rule, Category, UploadResume
from processors.expense_upload_processor import ExpenseUploadProcessor

class Command(BaseCommand):
    help = 'Resumes CSV uploads that were interrupted by a server shutdown'

    def handle(self, *args, **options):
        # Find uploads that never finished and are not already being processed by another command instance
        incomplete_uploads = CsvUpload.objects.filter(
            status='processing',
            resume_info__isnull=True
        )
        
        if not incomplete_uploads.exists():
            self.stdout.write("No interrupted uploads found.")
            return

        for upload in incomplete_uploads:
            try:
                # Attempt to create a resume entry to "lock" this upload
                # Only the command can update/delete this entry
                resume_entry = UploadResume.objects.create(csv_upload=upload)
            except IntegrityError:
                self.stdout.write(f"Upload {upload.id} is already being processed by another command instance.")
                continue

            try:
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
                
                # If completed, the related entry is deleted
                resume_entry.delete()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error resuming Upload {upload.id}: {str(e)}"))
                resume_entry.delete()
