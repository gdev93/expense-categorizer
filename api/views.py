from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect


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
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')

        # Create the user
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            last_name=last_name
        )

        # Auto-login after registration
        login(request, user)

        next_redirect_target = request.POST.get('next', '/')
        return redirect(next_redirect_target)

    # If GET request, redirect to registration form
    return redirect('register_form')
@login_not_required
def authenticate_user(request):
    username = request.POST.get('username')
    password = request.POST.get('password')
    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
    next_redirect_target = request.POST.get('next', '/')
    return redirect(next_redirect_target)


# Create your views here.
def index(request):
    user = request.user
    return render(
        request=request,
        template_name='main/index.html',
        context={'user_avatar': user.username[0].capitalize(),
                 'user_name': f"{user.first_name} {user.last_name}",
                 'users_active': True,
                 'main_content': 'users/users.html'
                 }

    )