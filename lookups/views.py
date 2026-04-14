from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated

from .models import (
    Mood,
    ContextCategory,
    DetailCategoryTree,
    NoteMarker,
    Occupation,
    EducationLevel,
    ClosenessScore,
    MediaType,
    JournalTag,
)

from .serializers import (
    MoodSerializer,
    ContextCategorySerializer,
    DetailCategorySerializer,
    NoteMarkerSerializer,
    OccupationSerializer,
    EducationLevelSerializer,
    ClosenessScoreSerializer,
    MediaTypeSerializer,
    JournalTagSerializer,
)


class MoodViewSet(ReadOnlyModelViewSet):
    """
    GET /api/lookups/moods/ - List available moods (system defaults + user-defined).
    Permission: IsAuthenticated
    """
    serializer_class = MoodSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Mood.objects.none()
        return Mood.objects.for_user(self.request.user)


class ContextCategoryViewSet(ReadOnlyModelViewSet):
    serializer_class = ContextCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ContextCategory.objects.none()
        return ContextCategory.objects.for_user(self.request.user)


class DetailCategoryViewSet(ReadOnlyModelViewSet):
    serializer_class = DetailCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return DetailCategoryTree.objects.none()
        return DetailCategoryTree.objects.for_user(self.request.user)


class NoteMarkerViewSet(ReadOnlyModelViewSet):
    serializer_class = NoteMarkerSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return NoteMarker.objects.none()
        return NoteMarker.objects.for_user(self.request.user)


class OccupationViewSet(ReadOnlyModelViewSet):
    serializer_class = OccupationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Occupation.objects.none()
        return Occupation.objects.for_user(self.request.user)


class EducationLevelViewSet(ReadOnlyModelViewSet):
    serializer_class = EducationLevelSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return EducationLevel.objects.none()
        return EducationLevel.objects.for_user(self.request.user)


class ClosenessScoreViewSet(ReadOnlyModelViewSet):
    serializer_class = ClosenessScoreSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ClosenessScore.objects.none()
        return ClosenessScore.objects.for_user(self.request.user)


class MediaTypeViewSet(ReadOnlyModelViewSet):
    serializer_class = MediaTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return MediaType.objects.none()
        return MediaType.objects.for_user(self.request.user)


class JournalTagViewSet(ReadOnlyModelViewSet):
    serializer_class = JournalTagSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return JournalTag.objects.none()
        return JournalTag.objects.for_user(self.request.user)