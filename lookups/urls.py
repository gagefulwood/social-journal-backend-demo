from rest_framework.routers import DefaultRouter
from .views import (
    MoodViewSet, 
    ContextCategoryViewSet, 
    FactCategoryViewSet,
    ObservationMarkerViewSet, 
    OccupationViewSet, 
    EducationLevelViewSet,
    MediaTypeViewSet, 
    EntryTagViewSet,
)

router = DefaultRouter()
router.register("moods",              MoodViewSet,            basename="mood")
router.register("context-categories", ContextCategoryViewSet, basename="context-category")
router.register("fact-categories",    FactCategoryViewSet,    basename="fact-category")
router.register("observation-markers", ObservationMarkerViewSet, basename="observation-marker")
router.register("occupations",        OccupationViewSet,      basename="occupation")
router.register("education-levels",   EducationLevelViewSet,  basename="education-level")
router.register("media-types",        MediaTypeViewSet,       basename="media-type")
router.register("entry-tags",         EntryTagViewSet,        basename="entry-tag")

urlpatterns = router.urls
