from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.utils import timezone

from .models import Event, EVENT_TIER_MILESTONE, EVENT_TIER_ROUTINE
from .filters import EventFilter
from .serializers import EventSerializer, EventListSerializer
from core.pagination import StandardResultsPagination
from core.permissions import IsOwner

class EventViewSet(ModelViewSet):
    '''
    POST /api/events/ -> Create a new event with optional participant contact IDs
    GET /api/events/ -> List authenticated user's events ordered by timestamp descending
    PATCH /api/events/{id}/ -> Update mutable event fields and replace participants
    DELETE /api/events/{id}/ -> Delete an event and cascade participants/journals
    '''
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    pagination_class = StandardResultsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = EventFilter

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
            .select_related("context_category", "interaction_mode", "mood")
            .prefetch_related(
                "participants__contact",
                "logs",
                "reflections",
                "exercises",
            )
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"], url_path="timeline-summary")
    def timeline_summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)

        return Response({
            "total_moments": queryset.count(),
            "upcoming": queryset.filter(event_timestamp__gt=now).count(),
            "routine": queryset.filter(tier=EVENT_TIER_ROUTINE).count(),
            "milestone": queryset.filter(tier=EVENT_TIER_MILESTONE).count(),
            "this_month": queryset.filter(
                event_timestamp__gte=month_start,
                event_timestamp__lt=next_month,
            ).count(),
            "with_mood": queryset.filter(mood__isnull=False).count(),
            "with_impact": queryset.filter(~Q(impact="")).count(),
        })
