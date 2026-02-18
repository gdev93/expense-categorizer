from django import forms
from django.contrib.auth.models import User
from allauth.account.forms import SignupForm, LoginForm as AllauthLoginForm
from django.core.exceptions import ValidationError

class LoginForm(AllauthLoginForm):
    """
    Custom login form that allows authentication with username or email.
    The label for the identification field is set to 'Nome utente o Email'.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['login'].label = "Nome utente o Email"
        self.fields['login'].widget.attrs.update({
            'placeholder': 'Nome utente o Email',
            'class': 'form-control',
            'autofocus': True
        })
        self.fields['password'].label = "Password"
        self.fields['password'].widget.attrs.update({
            'placeholder': 'Password',
            'class': 'form-control'
        })

class RegistrationForm(SignupForm):
    """
    Custom registration form with Italian labels and password confirmation.
    Inherits from allauth SignupForm.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            self.fields['username'].label = "Nome utente"
            self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Nome utente'})
        if 'email' in self.fields:
            self.fields['email'].label = "Email"
            self.fields['email'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Email'})
        if 'password1' in self.fields:
            self.fields['password1'].label = "Password"
            self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Password'})
        if 'password2' in self.fields:
            self.fields['password2'].label = "Conferma password"
            self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Conferma password'})
