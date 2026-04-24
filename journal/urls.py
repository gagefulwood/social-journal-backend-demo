from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers
from .views import JournalEntryViewSet, ReflectionViewSet

router = DefaultRouter()
router.register('', JournalEntryViewSet, basename='journal')

journal_router = nested_routers.NestedDefaultRouter(router, '', lookup='entry')
journal_router.register('reflections', ReflectionViewSet, basename='journal-reflection')

urlpatterns = router.urls + journal_router.urls