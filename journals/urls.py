from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    EmotionStateViewSet,
    EpisodeCategoryViewSet,
    EpisodeCharacteristicViewSet,
    EpisodeContextTagViewSet,
    InteractionDynamicViewSet,
    JournalFeedView,
    LogPatternView,
    LogViewSet,
    ReflectionViewSet,
    SocialEnergyFactorViewSet,
)


router = DefaultRouter()
router.register('logs', LogViewSet, basename='journal-log')
router.register('reflections', ReflectionViewSet, basename='journal-reflection')
router.register(
    'lookups/episode-categories',
    EpisodeCategoryViewSet,
    basename='journal-episode-category',
)
router.register(
    'lookups/episode-characteristics',
    EpisodeCharacteristicViewSet,
    basename='journal-episode-characteristic',
)
router.register(
    'lookups/episode-context-tags',
    EpisodeContextTagViewSet,
    basename='journal-episode-context-tag',
)
router.register(
    'lookups/social-energy-factors',
    SocialEnergyFactorViewSet,
    basename='journal-social-energy-factor',
)
router.register(
    'lookups/emotion-states',
    EmotionStateViewSet,
    basename='journal-emotion-state',
)
router.register(
    'lookups/interaction-dynamics',
    InteractionDynamicViewSet,
    basename='journal-interaction-dynamic',
)

urlpatterns = [
    path('', JournalFeedView.as_view(), name='journal-feed'),
    path('log-patterns/', LogPatternView.as_view(), name='journal-log-patterns'),
] + router.urls
