import itertools
from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.contrib.auth.models import User
from api.models import Transaction, UploadFile, FileStructureMetadata, Merchant, Category
from processors.expense_upload_processor import ExpenseUploadProcessor

class EmbeddingUpdateLogicTest(TestCase):
    def setUp(self):
        import os
        os.environ['GEMINI_API_KEY'] = 'dummy'
        self.user = User.objects.create_user(username='testuser')
        # We need a representative merchant
        self.merchant = Merchant.objects.create(user=self.user, name="MerchantX")
        
        # Raw data with a structure that will generate a specific hash
        self.raw_data = {"col1": "val1", "col2": "val2", "col3": "val3"}
        self.row_hash = FileStructureMetadata.generate_tuple_hash(self.raw_data.keys())
        
        # Metadata for this structure, initially without blacklist
        self.file_structure = FileStructureMetadata.objects.create(
            row_hash=self.row_hash,
            template_blacklist=[]
        )
        
        # Two upload files with transactions of the same structure
        self.upload1 = UploadFile.objects.create(user=self.user, file_name="file1.csv")
        self.tx1 = Transaction.objects.create(
            user=self.user,
            upload_file=self.upload1,
            raw_data=self.raw_data,
            description="Noise MerchantX",
            merchant=self.merchant,
            status='categorized'
        )
        
        self.upload2 = UploadFile.objects.create(user=self.user, file_name="file2.csv")
        self.tx2 = Transaction.objects.create(
            user=self.user,
            upload_file=self.upload2,
            raw_data=self.raw_data,
            description="Noise MerchantX",
            merchant=self.merchant,
            status='categorized'
        )

    @patch('processors.expense_upload_processor.EmbeddingEngine')
    @patch('processors.expense_upload_processor.ExpenseUploadProcessor.find_template_words')
    def test_embedding_update_on_blacklist_population(self, mock_find_words, mock_embedding_engine):
        # 1. Setup mock for TemplateLearner
        mock_find_words.return_value = ["noise"]
        
        # 2. Setup mock for EmbeddingEngine
        mock_model = MagicMock()
        # Mock numpy array tolist() behavior
        class MockEmb:
            def __init__(self, val): self.val = val
            def tolist(self): return self.val
        
        mock_model.embed.side_effect = lambda texts: [ MockEmb([0.1] * 384) for _ in texts ]
        mock_embedding_engine.get_model.return_value = mock_model
        
        processor = ExpenseUploadProcessor(self.user)
        
        # 3. Call _post_process_transactions on upload1
        with patch.object(ExpenseUploadProcessor, '_categorize_remaining_transactions'):
            processor._post_process_transactions(self.upload1)
        
        # 4. Verify blacklist was updated
        self.file_structure.refresh_from_db()
        self.assertEqual(self.file_structure.template_blacklist, ["noise"])
        
        # 5. Verify transactions in BOTH uploads were updated
        self.tx1.refresh_from_db()
        self.tx2.refresh_from_db()
        
        self.assertIsNotNone(self.tx1.embedding)
        self.assertIsNotNone(self.tx2.embedding)
        
        # 6. Check that EmbeddingEngine was called with cleaned descriptions
        # We expect "merchantx" as the cleaned description
        
        embed_calls = []
        for call in mock_model.embed.call_args_list:
            embed_calls.extend(call[0][0])
            
        self.assertIn("merchantx", embed_calls)
        # Should be called for both tx1 and tx2 during _update_embeddings_for_structure
        self.assertEqual(embed_calls.count("merchantx"), 2)

    @patch('processors.expense_upload_processor.EmbeddingEngine')
    @patch('processors.expense_upload_processor.ExpenseUploadProcessor.find_template_words')
    def test_embedding_no_update_if_blacklist_already_exists(self, mock_find_words, mock_embedding_engine):
        # Populate blacklist beforehand
        self.file_structure.template_blacklist = ["existing"]
        self.file_structure.save()
        
        processor = ExpenseUploadProcessor(self.user)
        
        # Mock everything
        mock_model = MagicMock()
        mock_embedding_engine.get_model.return_value = mock_model
        
        with patch.object(ExpenseUploadProcessor, '_categorize_remaining_transactions'):
            processor._post_process_transactions(self.upload1)
        
        # find_template_words should NOT be called
        mock_find_words.assert_not_called()
        # embed should NOT be called
        mock_model.embed.assert_not_called()
