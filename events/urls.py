from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .detail_views import (
    EventChapterCollectionView,
    EventChapterDetailView,
    EventChapterMaterializeLegacyView,
    EventChapterReorderView,
    EventMediaCollectionView,
    EventMediaDetailView,
    EventMediaReorderView,
)
from .views import EventViewSet

router = DefaultRouter()
router.register(r'events', EventViewSet, basename='event')

urlpatterns = [
    path(
        'events/<int:event_id>/chapters/',
        EventChapterCollectionView.as_view(),
        name='event-chapter-list',
    ),
    path(
        'events/<int:event_id>/chapters/reorder/',
        EventChapterReorderView.as_view(),
        name='event-chapter-reorder',
    ),
    path(
        'events/<int:event_id>/chapters/materialize-legacy/',
        EventChapterMaterializeLegacyView.as_view(),
        name='event-chapter-materialize-legacy',
    ),
    path(
        'events/<int:event_id>/chapters/<uuid:chapter_id>/',
        EventChapterDetailView.as_view(),
        name='event-chapter-detail',
    ),
    path(
        'events/<int:event_id>/media/',
        EventMediaCollectionView.as_view(),
        name='event-media-list',
    ),
    path(
        'events/<int:event_id>/media/reorder/',
        EventMediaReorderView.as_view(),
        name='event-media-reorder',
    ),
    path(
        'events/<int:event_id>/media/<uuid:attachment_id>/',
        EventMediaDetailView.as_view(),
        name='event-media-detail',
    ),
    path('', include(router.urls)),
]
