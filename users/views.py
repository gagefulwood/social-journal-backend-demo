from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.utils import extend_schema
import pyotp

from django.conf import settings
from users.models import Users

from .cookies import build_auth_metadata, clear_token_cookies, role_for_user, set_token_cookies
from .serializers import (
    UserRegistrationSerializer,
    CustomTokenObtainPairSerializer,
    UserPublicSerializer,
    MFASetupSerializer,
    MFAVerifySerializer,
)

class RegisterView(generics.CreateAPIView):
    '''
    POST /api/auth/register/ - Register a new user account.
    Returns 201 with public user fields on success.
    Returns 400 with field-level errors on validation failure.
    Permission: AllowAny
    '''
    serializer_class = UserRegistrationSerializer
    permissions_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserPublicSerializer(user).data,
            status=status.HTTP_201_CREATED
        )

class CustomTokenObtainPairView(TokenObtainPairView):
    '''
    POST /api/auth/token/ - Authenticate and obtain JWT token pair.
    Sets access and refresh tokens as httpOnly cookies.
    Response body contains non-sensitive auth metadata only.
    JWT payload includes: role, mfa_enabled, mfa_pending.
    Permission: AllowAny
    '''
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        access_token = validated_data.pop('access_token')
        refresh_token = validated_data.pop('refresh_token')
        response = Response(validated_data, status=status.HTTP_200_OK)
        return set_token_cookies(response, access_token, refresh_token)


class CookieTokenRefreshView(TokenRefreshView):
    '''
    POST /api/auth/token/refresh/ - Refresh auth cookies.
    Reads refresh token from the httpOnly refresh cookie.
    Rotates auth cookies on success and returns non-sensitive metadata only.
    Permission: AllowAny
    '''
    serializer_class = TokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not refresh_token:
            return Response(
                {'detail': 'Refresh cookie is required.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            refresh = RefreshToken(refresh_token)
            user = Users.objects.get(id=refresh[api_settings.USER_ID_CLAIM])
        except (TokenError, Users.DoesNotExist):
            return Response(
                {'detail': 'Refresh token is invalid.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = self.get_serializer(data={'refresh': refresh_token})
        serializer.is_valid(raise_exception=True)
        token_data = serializer.validated_data
        response = Response(build_auth_metadata(user), status=status.HTTP_200_OK)
        return set_token_cookies(
            response,
            token_data['access'],
            token_data.get('refresh'),
        )

@extend_schema(exclude=True)
class LogoutView(APIView):
    '''
    POST /api/auth/logout/ - Invalidate the current session.
    Reads the refresh token from the httpOnly cookie, blacklists it when present,
    and clears access/refresh cookies.
    Permission: IsAuthenticated
    '''
    http_method_names = ['post', 'options']
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        response = Response(
            {'detail': 'Successfully logged out.'},
            status=status.HTTP_205_RESET_CONTENT,
        )
        try:
            refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
            if refresh_token:
                RefreshToken(refresh_token).blacklist()
            return clear_token_cookies(response)
        except TokenError:
            response = Response(
                {'detail': 'Token is invalid or already blacklisted.'},
                status=status.HTTP_400_BAD_REQUEST
            )
            return clear_token_cookies(response)

class UserProfileView(generics.RetrieveUpdateAPIView):
    '''
    GET  /api/users/me/ - Retrieve the authenticated user's profile.
    PATCH /api/users/me/ - Update the authenticated user's profile.
    Scoped to request.user — users can only access their own profile.
    Permission: IsAuthenticated
    '''
    serializer_class = UserPublicSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
    
@extend_schema(exclude=True)
class MFASetupView(APIView):
    '''
    GET /api/auth/mfa/setup/ - Generate and store a TOTP secret for the authenticated user.
    Returns the raw secret and otpauth URI for QR code generation on the frontend.
    Calling this endpoint again regenerates the secret, invalidating any previous setup.
    Permission: IsAuthenticated
    '''
    permission_classes = [IsAuthenticated]

    def get(self, request):
        secret = pyotp.random_base32()

        otpauth_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=request.user.email,
            issuer_name='Social Journal'
        )

        request.user.mfa_secret = secret
        request.user.save(update_fields=['mfa_secret'])

        serializer = MFASetupSerializer({'secret': secret, 'otpauth_uri': otpauth_uri})
        return Response(serializer.data, status=status.HTTP_200_OK)

@extend_schema(exclude=True)
class MFAVerifyView(APIView):
    '''
    POST /api/auth/mfa/verify/ - Verify a TOTP code against the user's stored mfa_secret.
    On success: sets is_mfa_enabled=True on the user record.
    On failure: returns 400 with descriptive error.
    Permission: IsAuthenticated
    '''
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFAVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        totp_code = serializer.validated_data['totp_code']
        mfa_secret = request.user.mfa_secret

        if not mfa_secret:
            return Response(
                {'detail': 'MFA setup has not been initiated. Call GET /api/auth/mfa/setup/ first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        totp = pyotp.TOTP(mfa_secret)
        if not totp.verify(totp_code):
            return Response(
                {'detail': 'Invalid TOTP code. Please try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        request.user.is_mfa_enabled = True
        request.user.save(update_fields=['is_mfa_enabled'])

        refresh = RefreshToken.for_user(request.user)
        refresh['mfa_pending'] = False
        refresh['mfa_enabled'] = True
        refresh['role'] = role_for_user(request.user)

        response = Response(
            {
                'detail': 'MFA successfully enabled.',
                **build_auth_metadata(request.user, mfa_pending=False),
            },
            status=status.HTTP_200_OK,
        )
        return set_token_cookies(response, refresh.access_token, refresh)
