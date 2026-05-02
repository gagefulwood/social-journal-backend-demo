from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ExerciseViewSet, JournalFeedView, LogViewSet, ReflectionViewSet

router = DefaultRouter()
router.register('logs', LogViewSet, basename='journal-log')
router.register('reflections', ReflectionViewSet, basename='journal-reflection')
router.register('exercises', ExerciseViewSet, basename='journal-exercise')

urlpatterns = [
    path('', JournalFeedView.as_view(), name='journal-feed'),
] + router.urls
