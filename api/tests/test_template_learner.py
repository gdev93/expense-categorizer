from django.test import TestCase
from django.contrib.auth.models import User
from api.models import FileStructureMetadata, Transaction, Merchant, Category
from processors.template_learner import TemplateLearner, _normalize_description

class TemplateLearnerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser')
        self.file_structure = FileStructureMetadata.objects.create(
            row_hash='test_hash',
            description_column_name='Descrizione'
        )

    def test_normalize_description(self):
        # Test date removal
        text = "Spesa del 27/01/2026"
        self.assertEqual(_normalize_description(text), "spesa del")
        
        # Test time removal
        text = "Alle ore 13:49"
        self.assertEqual(_normalize_description(text), "alle ore")
        
        # Test long ID removal
        text = "ID 123456789012"
        self.assertEqual(_normalize_description(text), "id")
        
        # Combined test
        text = "Spesa del 27/01/2026 alle 13:49 ID 123456789012 con VISA"
        self.assertEqual(_normalize_description(text), "spesa del alle id con visa")

    def test_run_scaffolding(self):
        learner = TemplateLearner()
        # Should return empty list as there are no transactions
        self.assertEqual(learner.find_template_words([]), [])
