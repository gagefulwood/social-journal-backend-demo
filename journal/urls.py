from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers
from .views import JournalEntryViewSet, ReflectionViewSet

router = DefaultRouter()
router.register('entries', JournalEntryViewSet, basename='journal-entry')

entries_router = nested_routers.NestedDefaultRouter(router, 'entries', lookup='entry')
entries_router.register('reflections', ReflectionViewSet, basename='entry-reflection')

urlpatterns = router.urls + entries_router.urls