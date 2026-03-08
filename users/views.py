from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import (
    UserRegistrationSerializer,
    CustomTokenObtainPairSerializer,
    UserPublicSerializer,
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
