from django import forms
from django.contrib.auth.models import User
from allauth.account.forms import SignupForm, LoginForm as AllauthLoginForm
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from api.models import Transaction, Category


class TransactionForm(forms.ModelForm):
    description = forms.CharField(widget=forms.Textarea, required=False)
    amount = forms.DecimalField(max_digits=10, decimal_places=2, required=False)

    class Meta:
        model = Transaction
        fields = ['transaction_date', 'category']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial['description'] = self.instance.description
            self.initial['amount'] = self.instance.amount

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.description = self.cleaned_data.get('description')
        instance.amount = self.cleaned_data.get('amount')
        if commit:
            instance.save()
        return instance


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Food'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'e.g. Supermarket expenses...'
            }),
        }
        labels = {
            'name': 'Category Name',
            'description': 'Description (Optional)'
        }


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


class UploadFileForm(forms.Form):
    """Form for CSV/Excel file upload with validation"""

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

    file = forms.FileField(
        label='Transaction File',
        help_text='Upload a CSV or Excel file (max 10MB)',
        widget=forms.FileInput(attrs={
            'accept': '.csv,.xlsx,.xls',
            'class': 'form-control'
        }),
        validators=[
            FileExtensionValidator(allowed_extensions=['csv', 'xlsx', 'xls'])
        ]
    )

    def clean_file(self):
        """Validate uploaded file"""
        from processors.file_parsers import FileParserError
        file = self.cleaned_data.get('file')

        if not file:
            return file

        # Check file extension
        allowed_extensions = ('.csv', '.xlsx', '.xls')
        if not file.name.lower().endswith(allowed_extensions):
            raise forms.ValidationError('File must be a CSV or Excel file.')

        # Check file size
        if file.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError(
                f'File size must not exceed {self.MAX_FILE_SIZE / (1024 * 1024):.0f}MB.'
            )

        # Validate file content based on type
        try:
            # Validate that file has content
            if len(file) == 0:
                raise forms.ValidationError('File is empty.')

            file.seek(0)  # Reset file pointer

        except FileParserError as e:
            raise forms.ValidationError(str(e))
        except Exception as e:
            raise forms.ValidationError(f'Error reading file: {str(e)}')

        return file
