import os
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models





# Create your models here.
# class UserProfile(models.Model):
#     username = models.CharField(max_length=150, unique=True)
#     name = models.CharField(max_length=255)
#     phone = models.CharField(max_length=20,unique=True)
#     email = models.EmailField(unique=True)
#     password = models.CharField(max_length=128)

#     REQUIRED_FIELDS = ['email', 'name', 'phone']
#     USERNAME_FIELD = 'username'

#     def __str__(self):
#         return self.username


class UserProfileManager(BaseUserManager):
    def create_user(self, username, email, name, phone, password=None):
        if not email:
            raise ValueError('The Email field is required')
        if not username:
            raise ValueError('The Username field is required')

        user = self.model(
            username=username,
            email=self.normalize_email(email),
            name=name,
            phone=phone,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, name, phone, password=None):
        user = self.create_user(username, email, name, phone, password)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user

class UserProfile(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('user', 'User'),
    ]
    username = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    profile_image = models.TextField(blank=True, null=True)  # stores base64 data URL
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=10,
        choices=[('Active', 'Active'), ('Inactive', 'Inactive')],
        default='Active'  # Add this default value
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')  # Role field
    
    date_joined = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    objects = UserProfileManager()


    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'name', 'phone']

    def __str__(self):
        return self.username

from django.db import models

from django.db import models

class HelpMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=15)
    subject = models.CharField(max_length=150)
    message = models.TextField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.subject}"


# vision/models.py
from django.conf import settings
from django.db import models

class Feedback(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Use the custom user model
    feedback = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback from {self.user.username} on {self.created_at}"

# models.py
from django.db import models
from django.conf import settings

class UploadHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    image = models.TextField(blank=True, null=True)  # base64 data URL
    detected_objects = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.uploaded_at}"

