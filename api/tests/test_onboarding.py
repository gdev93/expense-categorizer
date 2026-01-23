import pytest
from django.contrib.auth.models import User
from django.urls import reverse

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
