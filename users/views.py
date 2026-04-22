from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema
import pyotp

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
    Returns access token (30 min) and refresh token (7 days).
    JWT payload includes: role, mfa_enabled, mfa_pending.
    Permission: AllowAny
    '''
    serializer_class = CustomTokenObtainPairSerializer

@extend_schema(exclude=True)
class LogoutView(generics.CreateAPIView):
    '''
    POST /api/auth/logout/ - Invalidate the current session.
    Accepts: { refresh: "<token>" } in request body.
    Blacklists the refresh token via SimpleJWT token_blacklist.
    Returns 205 on success, 400 if token is missing or already blacklisted.
    Permission: IsAuthenticated
    '''
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if not refresh_token:
                return Response(
                    {'detail': 'Refresh token is required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {'detail': 'Successfully logged out.'},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except TokenError:
            return Response(
                {'detail': 'Token is invalid or already blacklisted.'},
                status=status.HTTP_400_BAD_REQUEST
            )

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

        # Issue fresh tokens with mfa_pending=False so middleware allows on frontend
        refresh = RefreshToken.for_user(request.user)
        refresh['mfa_pending'] = False
        refresh['mfa_enabled'] = True
        try:
            refresh['role'] = request.user.groups.first().name if request.user.groups.exists() else 'Standard User'
        except Exception:
            refresh['role'] = 'Standard User'
        
        return Response(
            {'detail': 'MFA successfully enabled.',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            }, status=status.HTTP_200_OK)