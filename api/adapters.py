import os

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.db import transaction
from api.models import Profile

class AccountAdapter(DefaultAccountAdapter):

    def is_open_for_signup(self, request):
        """
        Checks whether or not the site is open for signups.
        """
        return True

    def get_site_name(self):
        return settings.SITE_NAME

    # Optional: ensure the confirmation URL uses your SITE_DOMAIN variable
    def get_email_confirmation_url(self, request, emailconfirmation):
        protocol = 'https' if request.is_secure() else 'http'
        return f"{protocol}://{settings.SITE_NAME}/accounts/confirm-email/{emailconfirmation.key}/"


    def save_user(self, request, user, form, commit=True):
        """
        Saves a newly signed up user and creates their profile.
        """
        user = super().save_user(request, user, form, commit=commit)
        with transaction.atomic():
            Profile.objects.get_or_create(user=user, defaults={'subscription_type': 'free_trial'})
        return user


class SocialAccountAdapter(DefaultSocialAccountAdapter):

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social user and creates their profile.
        """
        user = super().save_user(request, sociallogin, form)
        with transaction.atomic():
            Profile.objects.get_or_create(user=user, defaults={'subscription_type': 'free_trial'})
        return user