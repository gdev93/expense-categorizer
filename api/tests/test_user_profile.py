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
    url = reverse('create_user')
    data = {
        'username': 'newuser',
        'password': 'password123',
        'email': 'authorized@example.com',
        'first_name': 'New',
        'last_name': 'User'
    }
    
    # Mock allowed_emails to include our test email
    with patch('api.views.entry_point_views.allowed_emails', ['authorized@example.com']):
        response = client.post(url, data)
    
    assert response.status_code == 302  # Redirect after success
    
    user = User.objects.get(username='newuser')
    assert user.email == 'authorized@example.com'
    
    # Check if profile exists
    profile = Profile.objects.filter(user=user).first()
    assert profile is not None
    assert profile.subscription_type == 'free_trial'
