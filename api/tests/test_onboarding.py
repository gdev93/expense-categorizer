import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from api.models import Profile, Category, UploadFile

@pytest.mark.django_db
class TestOnboarding:
    def setup_method(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.profile = Profile.objects.create(user=self.user, onboarding_step=5) # Completed

    def test_onboarding_update_step_advance(self, client):
        client.login(username='testuser', password='password123')
        self.profile.onboarding_step = 1
        self.profile.save()
        
        url = reverse('update_onboarding_step')
        response = client.post(url, {'step': '2'})
        
        assert response.status_code == 200
        self.profile.refresh_from_db()
        assert self.profile.onboarding_step == 2

    def test_onboarding_reset_to_one(self, client):
        client.login(username='testuser', password='password123')
        # Already at step 5 (completed) from setup
        
        url = reverse('update_onboarding_step')
        response = client.post(url, {'step': '1'})
        
        assert response.status_code == 200
        self.profile.refresh_from_db()
        assert self.profile.onboarding_step == 1

    def test_onboarding_invalid_step(self, client):
        client.login(username='testuser', password='password123')
        
        url = reverse('update_onboarding_step')
        response = client.post(url, {'step': '6'})
        
        assert response.status_code == 400
        self.profile.refresh_from_db()
        assert self.profile.onboarding_step == 5

    def test_onboarding_advances_on_later_action(self, client):
        """
        Test that performing an action for step 2 (upload) advances onboarding
        even if current step is 1 (categories).
        """
        client.login(username='testuser', password='password123')
        self.profile.onboarding_step = 1
        self.profile.save()
        
        # Perform step 2 action: upload a file
        csv_content = b"Date;Amount;Description\n2023-01-01;10.0;Test"
        csv_file = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
        
        url = reverse('transactions_upload')
        client.post(url, {'file': csv_file})
        
        self.profile.refresh_from_db()
        assert self.profile.onboarding_step == 3

    def test_onboarding_advances_on_filter_action_from_step_1(self, client):
        """
        Test that using filters (step 3 action) advances onboarding
        even if current step is 1.
        """
        client.login(username='testuser', password='password123')
        self.profile.onboarding_step = 1
        self.profile.save()
        
        # Perform step 3 action: use filters
        url = reverse('transaction_list') + "?category=1"
        client.get(url)
        
        self.profile.refresh_from_db()
        assert self.profile.onboarding_step == 4

    def test_onboarding_advances_to_completed_on_transaction_update(self, client):
        """
        Test that updating a transaction (step 4 action) advances onboarding
        to completed (step 5).
        """
        from api.models import Transaction, Merchant
        client.login(username='testuser', password='password123')
        self.profile.onboarding_step = 4
        self.profile.save()
        
        category = Category.objects.create(user=self.user, name="Category")
        merchant = Merchant.objects.create(user=self.user, name="Merchant")
        upload_file = UploadFile.objects.create(user=self.user, file_name="test.csv", dimension=100)
        transaction = Transaction.objects.create(
            user=self.user, 
            merchant=merchant, 
            upload_file=upload_file,
            amount=10.0, 
            transaction_date="2023-01-01",
            status='uncategorized'
        )
        
        # Perform step 4 action: update transaction category
        url = reverse('update_transaction_category')
        client.post(url, {
            'transaction_id': transaction.id,
            'category_id': category.id
        })
        
        self.profile.refresh_from_db()
        assert self.profile.onboarding_step == 5

    def test_onboarding_does_not_skip_steps_on_load(self, client):
        """
        Test that onboarding does NOT advance automatically if the user already has
        categories and uploads, allowing them to replay the tutorial from the start.
        """
        client.login(username='testuser', password='password123')
        self.profile.onboarding_step = 1
        self.profile.save()
        
        # User already has categories and uploads
        Category.objects.create(user=self.user, name="Existing Category")
        UploadFile.objects.create(user=self.user, file_name="existing.csv", dimension=100)
        
        # Navigate to any page
        url = reverse('transaction_list')
        client.get(url)
        
        self.profile.refresh_from_db()
        # Should NOT skip to step 3, should stay at step 1
        assert self.profile.onboarding_step == 1
