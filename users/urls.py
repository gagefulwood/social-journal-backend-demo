from django.urls import path
from .views import (
    RegisterView,
    CustomTokenObtainPairView,
    CookieTokenRefreshView,
    LogoutView,
    UserProfileView,
    MFASetupView,
    MFAVerifyView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('token/', CustomTokenObtainPairView.as_view(), name='auth-token'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='auth-token-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('mfa/setup/', MFASetupView.as_view(), name='auth-mfa-setup'),
    path('mfa/verify/', MFAVerifyView.as_view(), name='auth-mfa-verify'),
    path('me/', UserProfileView.as_view(), name='user-profile'),
]
