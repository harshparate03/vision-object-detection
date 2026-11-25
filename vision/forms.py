import re
from django import forms
from django.core.validators import RegexValidator
from .models import Feedback, HelpMessage, UserProfile

class SignUpForm(forms.ModelForm):
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'}),
        required=True
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Enter Username'}),
        error_messages={'required': 'Username is required!'}
    )
    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Enter Your Name'}),
        error_messages={'required': 'Name is required!'}
    )
    phone = forms.CharField(
        validators=[
            RegexValidator(r'^\+?1?\d{9,15}$', 'Phone number is invalid')
        ],
        widget=forms.TextInput(attrs={'placeholder': 'Enter Phone Number'}),
        error_messages={'required': 'Phone number is required!'}
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'Enter Email Address'}),
        error_messages={
            'required': 'Email address is required!',
            'invalid': 'Enter a valid email address!'
        }
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Create Password'}),
        min_length=8,
        error_messages={
            'required': 'Password is required!',
            'min_length': 'Password must be at least 8 characters long!'
        }
    )

    class Meta:
        model = UserProfile
        fields = ['username', 'name', 'phone', 'email', 'password']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match!')
        return cleaned_data
    

# class SignInForm(forms.Form):
#     email = forms.EmailField(widget=forms.TextInput(attrs={'placeholder': 'Enter email address'}))
#     password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password'}))

#     def clean(self):
#         cleaned_data = super().clean()
#         email = cleaned_data.get('email')

#         password = cleaned_data.get('password')

#         try:
#             user = UserProfile.objects.get(email=email)
#         except UserProfile.DoesNotExist:
#             raise ValidationError('Invalid credentials')  # Email not found

#         if not user.check_password(password):
#             raise ValidationError('Invalid credentials')  # Password incorrect

#         cleaned_data['user'] = user  # Save user for later use in the view
#         return cleaned_data


# class SignInForm(forms.Form):
#     username = forms.CharField(max_length=150, required=True)
#     password = forms.CharField(widget=forms.PasswordInput(), required=True)
    
#     def clean_username(self):
#         username = self.cleaned_data.get('username')
#         if not User.objects.filter(username=username).exists():
#             raise forms.ValidationError("Username does not exist.")
#         return username
    
#     def clean_password(self):
#         password = self.cleaned_data.get('password')
#         return password

from django.contrib.auth.backends import ModelBackend
from .models import UserProfile

# class EmailBackend(ModelBackend):
#     def authenticate(self, request, email=None, password=None, **kwargs):
#         try:
#             user = UserProfile.objects.get(email=email)
#             if user.check_password(password):
#                 return user
#         except UserProfile.DoesNotExist:
#             return None
#         return None

from django import forms
from .models import HelpMessage
import re

class HelpMessageForm(forms.ModelForm):
    class Meta:
        model = HelpMessage
        fields = ['name', 'email', 'phone_number', 'subject', 'message']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            raise forms.ValidationError("Invalid email format.")
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if not phone_number.isdigit() or len(phone_number) < 10:
            raise forms.ValidationError("Phone number must be at least 10 digits long.")
        return phone_number
    

# vision/forms.py
from django import forms
from .models import Feedback

class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['feedback']
        widgets = {
            'feedback': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Enter your feedback'}),
        }

from django import forms
from .models import UserProfile

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['username', 'name', 'phone', 'email', 'password' ,'status']

from django import forms
from django.utils.safestring import mark_safe
from .models import UserProfile

class CustomUserForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['name', 'username', 'email', 'phone', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter full name'
            }),
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'readonly': 'readonly',  # Read-only username
                'placeholder': 'Username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'readonly': 'readonly',  # Read-only email
                'placeholder': 'Email'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            # 'profile_image': forms.ClearableFileInput(attrs={
            #     'class': 'form-control'
            # })  # Allows file selection for new upload
        }

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)

    #     # If user has a profile image, show it
    #     if self.instance and self.instance.profile_image:
    #         self.fields['profile_image'].label = mark_safe(
    #             f'<img src="{self.instance.profile_image.url}" width="100" height="100" class="rounded-circle mb-2">'
    #         )
