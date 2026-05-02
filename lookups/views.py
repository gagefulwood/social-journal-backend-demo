from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import (
    Mood,
    ContextCategory,
    FactCategory,
    ObservationMarker,
    Occupation,
    EducationLevel,
    ClosenessScore,
    MediaType,
    JournalTag,
)

from .serializers import (
    MoodSerializer,
    ContextCategorySerializer,
    FactCategorySerializer,
    ObservationMarkerSerializer,
    OccupationSerializer,
    EducationLevelSerializer,
    ClosenessScoreSerializer,
    MediaTypeSerializer,
    JournalTagSerializer,
)

class WritableLookupViewSet(ModelViewSet):
    '''
    Base ViewSet for lookup tables that support user-custom values.
    GET returns system defaults + user-owned rows via LookupManager.for_user().
    POST creates a new row owned by the requesting user.
    No PATCH, PUT, or DELETE - lookup values are append-only.
    '''
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ['get', 'post', 'head', 'options']

    def perform_create(self, serializer):
        '''
        Always set user from request.user and is_system_default=False.
        Users can never create system defaults through the API.
        '''
        serializer.save(user=self.request.user, is_system_default=False)

class MoodViewSet(WritableLookupViewSet):
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


class ContextCategoryViewSet(WritableLookupViewSet):
    serializer_class = ContextCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ContextCategory.objects.none()
        return ContextCategory.objects.for_user(self.request.user)


class FactCategoryViewSet(WritableLookupViewSet):
    serializer_class = FactCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FactCategory.objects.none()
        return FactCategory.objects.filter(
            Q(is_system_default=True) | Q(user=self.request.user),
            parent__isnull=True,
        )


class ObservationMarkerViewSet(WritableLookupViewSet):
    serializer_class = ObservationMarkerSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ObservationMarker.objects.none()
        return ObservationMarker.objects.for_user(self.request.user)


class OccupationViewSet(WritableLookupViewSet):
    serializer_class = OccupationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Occupation.objects.none()
        return Occupation.objects.for_user(self.request.user)


class EducationLevelViewSet(WritableLookupViewSet):
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


class JournalTagViewSet(WritableLookupViewSet):
    serializer_class = JournalTagSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return JournalTag.objects.none()
        return JournalTag.objects.for_user(self.request.user)
