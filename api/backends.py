from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

class EmailOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend that allows users to authenticate using
    either their username or email address.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        
        try:
            # Use Q objects to check both username and email fields
            # We use iexact for case-insensitive matching if appropriate, 
            # but standard Django username is case-sensitive usually. 
            # However, for email it's often better to be case-insensitive.
            # The requirement just says "check both username and email fields".
            user = UserModel.objects.get(Q(username=username) | Q(email=username))
        except UserModel.DoesNotExist:
            # Handle non-existent users to prevent timing attacks by performing a password check simulation
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # Handle cases where multiple users might match
            # This could happen if a username is the same as another user's email
            # We return None as we cannot determine the correct user
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
