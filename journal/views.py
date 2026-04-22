from django.db.models import Q
from rest_framework import viewsets
from core.permissions import IsOwner
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from core.pagination import StandardResultsPagination
from core.throttles import ReflectionRateThrottle
from .models import JournalEntry, Reflection
from events.models import Event
from .serializers import JournalEntryListSerializer, JournalEntrySerializer, ReflectionSerializer
from .filters import JournalEntryFilter

class JournalEntryViewSet(viewsets.ModelViewSet):
    """
    POST   /api/journal/entries/        - Create a new journal entry linked to an event.
    GET    /api/journal/entries/        - List the authenticated user's journal entries.
    GET    /api/journal/entries/{id}/   - Retrieve a single journal entry.
    PATCH  /api/journal/entries/{id}/   - Update title/mood/tags only. Body is immutable.
    Permission: IsAuthenticated + IsOwner
    """
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    permission_classes = [IsAuthenticated, IsOwner]
    filterset_class = JournalEntryFilter
    pagination_class = StandardResultsPagination

    def get_serializer_class(self):
        if self.action == 'list':
            return JournalEntryListSerializer
        return JournalEntrySerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return JournalEntry.objects.none()
        return JournalEntry.objects.filter(
            Q(event__user=self.request.user) | Q(event__isnull=True, user=self.request.user)
        ).select_related('mood', 'event')

    def perform_create(self, serializer):
        event = None
        event_id = self.request.data.get('event_id')
        if event_id:
            try:
                event = Event.objects.get(pk=event_id)
            except Event.DoesNotExist:
                raise ValidationError('event_id is invalid or does not exist.')
            if event.user != self.request.user:
                raise PermissionDenied('You do not have permission to add a journal entry to this event.')
        serializer.save(event=event, user=self.request.user)

class ReflectionViewSet(viewsets.ModelViewSet):
    '''
    GET  /api/journal/entries/{entry_pk}/reflections/      - List reflections for a journal entry.
    POST /api/journal/entries/{entry_pk}/reflections/      - Add a reflection to a journal entry.
    Permission: IsAuthenticated
    Rate limit: One reflection per journal entry per 12 hours (ReflectionRateThrottle)
    '''
    http_method_names = ['get', 'post', 'head', 'options']
    permission_classes = [IsAuthenticated]
    throttle_classes = [ReflectionRateThrottle]
    serializer_class = ReflectionSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Reflection.objects.none()
        return Reflection.objects.filter(
            journal_entry_id=self.kwargs['entry_pk'],
            journal_entry__event__user=self.request.user,
        )

    def perform_create(self, serializer):
        try:
            journal_entry = JournalEntry.objects.get(
                pk=self.kwargs['entry_pk'],
                event__user=self.request.user,
            )
        except JournalEntry.DoesNotExist:
            raise PermissionDenied('Journal entry not found or you do not have permission.')
        serializer.save(journal_entry=journal_entry)
