from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import re
from .models import Users

class UserRegistrationSerializer(serializers.ModelSerializer):
    '''
    Validates and creates a new Users instance.
    Enforces password complexity: min 10 chars, one number, one special character.
    Strips password_confirm before saving. Hashes password via create_user().
    '''
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = Users
        fields = [
            'email', 'username', 'first_name', 'last_name',
            'phone_number', 'password', 'password_confirm',
        ]
    
    def validate_password(self, value):
        # Minimum 10 characters
        if len(value) < 10:
            raise serializers.ValidationError(
                "Password must be at least 10 characters long."
            )
        # Must contain a number
        if not re.search(r'\d', value):
            raise serializers.ValidationError(
                "Password must contain at least one number."
            )
        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', value):
            raise serializers.ValidationError(
                "Password must contain at least one special character."
            )
        return value
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': 'Passwords do not match'}
            )
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = Users.objects.create_user(**validated_data)
        return user

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    '''
    Extends SimpleJWT TokenObtainPairSerializer to inject custom claims into JWT payload.
    Adds: role (user Group name), mfa_enabled (bool), mfa_pending (bool).
    mfa_pending is read by Next.js middleware to redirect to /auth/mfa before granting session access.
    '''
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.groups.values_list('name', flat=True).first() or 'Standard User'
        token['mfa_enabled'] = user.is_mfa_enabled
        token['mfa_pending'] = user.is_mfa_enabled
        return token

class UserPublicSerializer(serializers.ModelSerializer):
    '''
    Read-only serializer for safe user profile exposure.
    Excludes: password_hash, mfa_secret, provider_uid.
    Used by RegisterView (201 response) and UserProfileView (GET/PATCH /api/users/me/).
    '''
    class Meta:
        model = Users
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'phone_number',
            'is_mfa_enabled', 'auth_provider',
        ]
        read_only_fields = fields


class MFASetupSerializer(serializers.Serializer):
    '''
    Read-only response serializer for MFA setup.
    Returns the raw TOTP secret and otpauth URI for QR code generation on the frontend.
    No input fields — secret is generated server-side.
    '''
    secret = serializers.CharField(read_only=True)
    otpauth_uri = serializers.CharField(read_only=True)

class MFAVerifySerializer(serializers.Serializer):
    '''
    Accepts a 6-digit TOTP code from the frontend.
    Validated against the user's stored mfa_secret via pyotp.TOTP().verify().
    '''
    totp_code = serializers.CharField(
        required=True,
        min_length=6,
        max_length=6,
        help_text="6-digit code from authenticator app."
    )