from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch
from processors.file_parsers import FileParserError
from api.models import UploadFile
import io

class UploadErrorHandlingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client = Client()
        self.client.login(username='testuser', password='password')
        self.upload_url = reverse('transactions_upload')

    @patch('api.views.upload_file_view.parse_uploaded_file')
    def test_parsing_error_returns_bad_request_or_json(self, mock_parse):
        # Mock parsing error
        mock_parse.side_effect = FileParserError('Test parsing error')
        
        # Create a dummy file
        csv_file = io.BytesIO(b"date,description,amount\n2023-01-01,test,10.00")
        csv_file.name = 'test.csv'
        
        # Regular post should still return 200 with HTML (legacy/fallback)
        response = self.client.post(self.upload_url, {'file': csv_file})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test parsing error')

    @patch('api.views.upload_file_view.parse_uploaded_file')
    def test_parsing_error_json_response(self, mock_parse):
        # This test checks if we get a JSON response when X-Requested-With header is present
        mock_parse.side_effect = FileParserError('Test parsing error')
        
        csv_file = io.BytesIO(b"date,description,amount\n2023-01-01,test,10.00")
        csv_file.name = 'test.csv'
        
        # Simulate an AJAX request by setting the header
        response = self.client.post(
            self.upload_url, 
            {'file': csv_file}, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Now it should return 400 Bad Request
        self.assertEqual(response.status_code, 400)
        
        # And it should be JSON with the error message
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('Test parsing error', data['error'])

    @patch('api.views.upload_file_view.parse_uploaded_file')
    def test_empty_file_error_json_response(self, mock_parse):
        # Mock empty file data
        mock_parse.return_value = []
        
        csv_file = io.BytesIO(b"")
        csv_file.name = 'empty.csv'
        
        response = self.client.post(
            self.upload_url, 
            {'file': csv_file}, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        # Check for both English and Italian as I might translate it
        self.assertTrue('empty' in data['error'].lower() or 'vuoto' in data['error'].lower())

    @patch('api.views.upload_file_view.CsvStructureDetector')
    @patch('api.views.upload_file_view.parse_uploaded_file')
    def test_invalid_structure_error_json_response(self, mock_parse, mock_detector_class):
        # Mock successful parsing but failed structure detection
        mock_parse.return_value = [{'col1': 'val1', 'col2': 'val2'}]
        
        # We need to return an UploadFile object that has NO mandatory columns set
        def side_effect_setup(file_data, upload_file, user):
            # Do nothing, leave columns as None
            return upload_file
        
        mock_detector_instance = mock_detector_class.return_value
        mock_detector_instance.setup_upload_file_structure.side_effect = side_effect_setup
        
        csv_file = io.BytesIO(b"wrong,columns\nvalue1,value2")
        csv_file.name = 'invalid.csv'
        
        # Count UploadFiles before
        count_before = UploadFile.objects.count()
        
        response = self.client.post(
            self.upload_url, 
            {'file': csv_file}, 
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('Struttura del file non riconosciuta', data['error'])
        self.assertIn('data', data['error'])
        self.assertIn('descrizione', data['error'])
        self.assertIn('importo', data['error'])
        
        # Verify preliminary UploadFile was deleted
        self.assertEqual(UploadFile.objects.count(), count_before)
