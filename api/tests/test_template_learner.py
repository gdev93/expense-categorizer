from django.test import TestCase
from django.contrib.auth.models import User
from api.models import FileStructureMetadata
from processors.template_learner import TemplateLearner

class TemplateLearnerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser')
        self.file_structure = FileStructureMetadata.objects.create(
            row_hash='test_hash',
            description_column_name='Descrizione'
        )

    def test_normalize_description(self):
        learner = TemplateLearner(self.user, self.file_structure)
        
        # Test date removal
        text = "Operazione del 27/01/2026"
        self.assertEqual(_normalize_description(text), "Operazione del")
        
        # Test time removal
        text = "Alle ore 13:49"
        self.assertEqual(_normalize_description(text), "Alle ore")
        
        # Test long ID removal
        text = "ID 123456789012"
        self.assertEqual(_normalize_description(text), "ID")
        
        # Combined test
        text = "Operazione del 27/01/2026 alle 13:49 ID 123456789012 con MASTERCARD"
        self.assertEqual(_normalize_description(text), "Operazione del alle con MASTERCARD")

    def test_run_scaffolding(self):
        learner = TemplateLearner(self.user, self.file_structure)
        # Should return empty list as it's a placeholder
        self.assertEqual(learner.find_template_words(), [])
