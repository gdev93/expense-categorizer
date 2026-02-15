import os
from pathlib import Path

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, BadRequest
from django.db import transaction, IntegrityError
from django.shortcuts import render, redirect

from api.models import Profile

def load_allowed_emails():
    """Load allowed emails from allowed_emails.txt file"""
    file_path = Path(__file__).resolve().parent.parent.parent / 'allowed-emails.txt'
    try:
        with open(file_path, 'r') as f:
            # Strip whitespace and skip empty lines
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        # Fallback to empty list if file doesn't exist
        return []

allowed_emails = load_allowed_emails()

# Create your views here.
@login_not_required
def login_form(request):
    return render(
        request=request,
        template_name='accounts/account.html'
    )


@login_not_required
def register_form(request):
    return render(
        request=request,
        template_name='accounts/register.html'
    )


@login_not_required
def create_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email', '')

        if not username or not password or not email:
            raise BadRequest("Username, password, and email are required.")

        if email not in allowed_emails:
            raise PermissionDenied("Email not authorized.")
        user_exists = User.objects.filter(username=username).exists()
        if user_exists:
            raise PermissionDenied("Username already exists. Ask giacomozanotti.dev@gmail.com to reset password.")
        # Create the user
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email
            )
            Profile.objects.create(user=user,subscription_type='free_trial')

        # Auto-login after registration
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        next_redirect_target = request.POST.get('next', '/')
        return redirect(next_redirect_target)

    # If GET request, redirect to registration form
    return redirect('register_form')
@login_not_required
def authenticate_user(request):
    username = request.POST.get('username')
    password = request.POST.get('password')

    if not username or not password:
        raise BadRequest("Username and password are required.")

    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
    next_redirect_target = request.POST.get('next', '/')
    return redirect(next_redirect_target)


def logout_user(request):
    logout(request)
    return redirect('login_form')


# Create your views here.
def index(request):
    user = request.user
    return render(
        request=request,
        template_name='main/index.html',
        context={'user_avatar': user.username[0].capitalize(),
                 'user_name': f"{user.first_name} {user.last_name}",
                 'main_content': 'users/users.html'
                 }

    )