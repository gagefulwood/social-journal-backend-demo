from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Event
from .serializers import EventSerializer
from core.pagination import StandardResultsPagination

class EventViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet):
    '''
    POST /api/events/ -> Create a new event with optional participant contact IDs
    GET /api/events/ -> List authenticated user's events ordered by timestamp descending

    Create and list only for Sprint 2 **
    Retrieve, update, and delete added in Sprint 3 with full journal entry feature **
    '''
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Event.objects.none()
        return Event.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)