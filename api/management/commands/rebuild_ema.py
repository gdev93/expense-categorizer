import logging
import itertools
from typing import Any, Iterable

from django.core.management import BaseCommand
from api.models import MerchantEMA, Transaction, Merchant, FileStructureMetadata
from processors.similarity_matcher import update_merchant_ema
from processors.embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Rebuilds the Exponential Moving Average (EMA) of the digital footprint for each merchant/file-structure pair.'

    def handle(self, *args: Any, **options: Any) -> None:
        """
        Rebuilds the EMA for each Merchant by clearing existing data and re-processing transactions.
        """
        # Clear existing MerchantEMA records
        self.stdout.write(self.style.WARNING("Clearing all existing MerchantEMA records..."))
        MerchantEMA.objects.all().delete()

        # Fetch all transactions with necessary links, sorted for grouping and chronological order
        transactions_qs = Transaction.objects.filter(
            merchant__isnull=False,
            upload_file__file_structure_metadata__isnull=False
        ).select_related('merchant', 'upload_file__file_structure_metadata').order_by(
            'merchant_id', 'upload_file__file_structure_metadata_id', 'transaction_date', 'created_at'
        )

        total_tx = transactions_qs.count()
        if total_tx == 0:
            self.stdout.write(self.style.SUCCESS("No transactions to process."))
            return

        self.stdout.write(f"Found {total_tx} transactions to process.")

        model = EmbeddingEngine.get_model()

        def key_func(tx: Transaction) -> tuple[int, int]:
            # This is safe because of the filter and select_related
            return (tx.merchant.id, tx.upload_file.file_structure_metadata.id)

        processed_count = 0
        # Use iterator for memory efficiency
        for key, group in itertools.groupby(transactions_qs.iterator(chunk_size=1000), key_func):
            tx_list = [tx for tx in group if tx.description]
            if not tx_list:
                continue

            merchant = tx_list[0].merchant
            fs_metadata = tx_list[0].upload_file.file_structure_metadata
            
            descriptions = [tx.description for tx in tx_list]
            
            try:
                # Batch generate embeddings for the current merchant/file-structure group
                embeddings = list(model.embed(descriptions))
                
                for tx, embedding_vec in zip(tx_list, embeddings):
                    update_merchant_ema(
                        merchant=merchant,
                        file_structure_metadata=fs_metadata,
                        embedding=embedding_vec.tolist()
                    )
                
                processed_count += len(tx_list)
                if processed_count % 100 == 0 or processed_count == total_tx:
                    self.stdout.write(f"Processed {processed_count}/{total_tx} transactions...")
                    
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error processing group {key}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS("Rebuild of MerchantEMA completed successfully."))
