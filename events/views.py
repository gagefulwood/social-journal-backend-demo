from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Event
from .serializers import EventSerializer, EventListSerializer
from core.pagination import StandardResultsPagination
from core.permissions import IsOwner

class EventViewSet(ModelViewSet):
    '''
    POST /api/events/ -> Create a new event with optional participant contact IDs
    GET /api/events/ -> List authenticated user's events ordered by timestamp descending

    Create and list only for Sprint 2 **
    Retrieve, update, and delete added in Sprint 3 with full journal entry feature **
    '''
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend]

    http_method_names = [
        "get",
        "post",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def get_serializer_class(self): 
        if self.action == "list":
            return EventListSerializer
        return EventSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Event.objects.none()

        return (
            Event.objects
            .filter(user=self.request.user)
            .select_related("context_category")
            .prefetch_related("participants__contact")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)