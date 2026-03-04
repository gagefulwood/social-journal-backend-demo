from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

class UsersManager(BaseUserManager):
    def create_user(self, email, username, first_name, last_name, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, first_name=first_name, last_name=last_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, first_name, last_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, username, first_name, last_name, password, **extra_fields)

class Users(AbstractBaseUser, PermissionsMixin):
    email        = models.EmailField(unique=True)
    username     = models.CharField(max_length=150, unique=True)
    first_name   = models.CharField(max_length=150)
    last_name    = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True)
    is_active    = models.BooleanField(default=True)
    is_staff     = models.BooleanField(default=False)
    is_mfa_enabled = models.BooleanField(default=False)
    mfa_secret   = models.CharField(max_length=64, blank=True)
    auth_provider  = models.CharField(max_length=50, blank=True)
    provider_uid   = models.CharField(max_length=255, blank=True)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    objects = UsersManager()

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email