from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Users


@admin.register(Users)
class UsersAdmin(UserAdmin):
    list_display  = ['email', 'username', 'first_name', 'last_name', 'is_mfa_enabled', 'is_active', 'is_staff']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering      = ['email']

    fieldsets = UserAdmin.fieldsets + (
        ('MFA', {'fields': ('is_mfa_enabled', 'mfa_secret')}),
        ('OAuth', {'fields': ('auth_provider', 'provider_uid')}),
        ('Contact', {'fields': ('phone_number',)}),
    )