from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import PermissionDenied
from api.views.entry_point_views import allowed_emails
from api.models import Profile
from django.db import transaction

class MySocialAccountAdapter(DefaultSocialAccountAdapter):

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly signed up social user and creates their profile.
        """
        user = super().save_user(request, sociallogin, form)
        with transaction.atomic():
            Profile.objects.get_or_create(user=user, defaults={'subscription_type': 'free_trial'})
        return user