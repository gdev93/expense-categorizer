import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from api.models import Profile
from unittest.mock import patch

@pytest.mark.django_db
def test_create_user_view_creates_profile(client):
    """
    Test that the create_user view creates both a User and a Profile.
    """
    url = reverse('account_signup')
    data = {
        'username': 'newuser',
        'password1': 'StR0ngP@ssw0rd!123',
        'password2': 'StR0ngP@ssw0rd!123',
        'email': 'authorized@example.com',
    }
    
    # Mock allowed_emails is no longer needed since we use allauth and AccountAdapter is open
    response = client.post(url, data)
    
    assert response.status_code == 302  # Redirect after success
    
    user = User.objects.get(username='newuser')
    assert user.email == 'authorized@example.com'
    
    # Check if profile exists
    profile = Profile.objects.filter(user=user).first()
    assert profile is not None
    assert profile.subscription_type == 'free_trial'
