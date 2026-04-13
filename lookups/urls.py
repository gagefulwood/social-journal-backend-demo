from rest_framework.routers import DefaultRouter
from .views import (
    MoodViewSet, 
    ContextCategoryViewSet, 
    DetailCategoryViewSet,
    NoteMarkerViewSet, 
    OccupationViewSet, 
    EducationLevelViewSet,
    ClosenessScoreViewSet, 
    MediaTypeViewSet, 
    JournalTagViewSet,
)

router = DefaultRouter()
router.register("moods",              MoodViewSet,            basename="mood")
router.register("context-categories", ContextCategoryViewSet, basename="context-category")
router.register("detail-categories",  DetailCategoryViewSet,  basename="detail-category")
router.register("note-markers",       NoteMarkerViewSet,      basename="note-marker")
router.register("occupations",        OccupationViewSet,      basename="occupation")
router.register("education-levels",   EducationLevelViewSet,  basename="education-level")
router.register("closeness-scores",   ClosenessScoreViewSet,  basename="closeness-score")
router.register("media-types",        MediaTypeViewSet,       basename="media-type")
router.register("journal-tags",       JournalTagViewSet,      basename="journal-tag")

urlpatterns = router.urls