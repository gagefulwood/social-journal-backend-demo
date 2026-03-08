from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    CustomTokenObtainPairView,
    LogoutView,
    UserProfileView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('token/', CustomTokenObtainPairView.as_view(), name='auth-token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', UserProfileView.as_view(), name='user-profile'),
]