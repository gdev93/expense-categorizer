from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch
from processors.file_parsers import FileParserError
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
