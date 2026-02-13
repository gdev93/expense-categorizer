from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import PermissionDenied
from api.views.entry_point_views import allowed_emails
from api.models import Profile
from django.db import transaction

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Checks if the email is in the allowed list before proceeding with login.
        """
        # # sociallogin.user is an unsaved User instance populated with data from the provider
        # email = sociallogin.user.email
        # if not email:
        #     # Fallback to check social account data directly if user.email is not yet set
        #     email = sociallogin.account.extra_data.get('email')
        #
        # if email not in allowed_emails:
        #     raise PermissionDenied("Email not authorized.")
        raise PermissionDenied

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social user and creates their profile.
        """
        user = super().save_user(request, sociallogin, form)
        with transaction.atomic():
            Profile.objects.get_or_create(user=user, defaults={'subscription_type': 'free_trial'})
        return user
