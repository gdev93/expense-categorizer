from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.db import transaction
from api.models import Profile



class AccountAdapter(DefaultAccountAdapter):

    def is_open_for_signup(self, request):
        """
        Checks whether or not the site is open for signups.
        """
        return True

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