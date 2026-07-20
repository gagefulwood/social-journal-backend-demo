from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    MediaAssetViewSet,
    MediaCapabilitiesView,
    MediaUploadCancelView,
    MediaUploadSessionDetailView,
)


router = DefaultRouter()
router.register('media', MediaAssetViewSet, basename='media')

urlpatterns = [
    path(
        'media/capabilities/',
        MediaCapabilitiesView.as_view(),
        name='media-capabilities',
    ),
    path(
        'media/uploads/cancel/',
        MediaUploadCancelView.as_view(),
        name='media-upload-cancel',
    ),
    path(
        'media/uploads/<uuid:pk>/',
        MediaUploadSessionDetailView.as_view(),
        name='media-upload-session-detail',
    ),
    path('', include(router.urls)),
]
