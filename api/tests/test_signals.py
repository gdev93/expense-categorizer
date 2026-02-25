import pytest
from django.core import mail
from django.contrib.auth.models import User
from allauth.account.signals import user_signed_up
from allauth.account.models import EmailAddress
from django.conf import settings

@pytest.mark.django_db
def test_backoffice_notification_on_signup(rf, settings):
    """
    Tests that a backoffice notification email is sent when a user signs up.
    """
    # Ensure backoffice email is set in settings
    settings.BACKOFFICE_EMAIL = 'backoffice@example.com'
    
    # Clear outbox
    mail.outbox = []
    
    # Mock request
    request = rf.get('/')
    
    # Create a user
    user = User.objects.create_user(
        username='testbackoffice', 
        email='testbackoffice@example.com', 
        password='password123'
    )
    
    # Create verified email address for the user (required by the signal handler)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    
    # Trigger the signal
    user_signed_up.send(sender=User, request=request, user=user)
    
    # Verify email was sent to backoffice
    backoffice_emails = [m for m in mail.outbox if settings.BACKOFFICE_EMAIL in m.to]
    assert len(backoffice_emails) == 1
    
    email = backoffice_emails[0]
    assert f"Nuovo utente registrato: {user.username}" in email.subject
    assert user.username in email.body
    assert user.email in email.body
    
    # Verify it has HTML content as well
    assert len(email.alternatives) == 1
    assert email.alternatives[0][1] == "text/html"
    assert user.username in email.alternatives[0][0]
