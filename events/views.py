from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import (
    BooleanField,
    Case,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Value,
    When,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import (
    EVENT_TIER_MILESTONE,
    EVENT_TIER_ROUTINE,
    Event,
    EventChapter,
    EventChapterParticipant,
    EventParticipant,
)
from .filters import EventFilter
from .serializers import (
    EventListSerializer,
    EventRelatedSerializer,
    EventSerializer,
)
from .services import ready_event_media_queryset
from core.pagination import StandardResultsPagination
from core.permissions import IsOwner
from journals.models import Log, Reflection

RELATED_EVENTS_DEFAULT_LIMIT = 2
RELATED_EVENTS_MAX_LIMIT = 10
RELATED_EVENT_REASON_WEIGHTS = {
    "shared_participant": 100,
    "same_context": 40,
    "same_interaction_mode": 20,
    "same_tier": 10,
}
RELATED_EVENT_REASON_SCORE_FIELDS = (
    ("shared_participant", "related_shared_participant_score"),
    ("same_context", "related_same_context_score"),
    ("same_interaction_mode", "related_same_interaction_mode_score"),
    ("same_tier", "related_same_tier_score"),
)


class EventViewSet(ModelViewSet):
    '''
    POST /api/events/ -> Create a new event with optional participant contact IDs
    GET /api/events/ -> List authenticated user's events, newest-first by default
    PATCH /api/events/{id}/ -> Update mutable event fields and replace participants
    DELETE /api/events/{id}/ -> Delete an event and unlink retained journals
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
        if self.action == "related":
            return EventRelatedSerializer
        return EventSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Event.objects.none()

        queryset = (
            Event.objects
            .filter(user=self.request.user)
            .order_by("-event_timestamp", "-id")
            .select_related(
                "user",
                "context_category",
                "interaction_mode",
                "mood",
            )
            .annotate(
                journal_log_exists=Exists(
                    Log.objects.filter(event_id=OuterRef("pk")),
                ),
                journal_reflection_exists=Exists(
                    Reflection.objects.filter(event_id=OuterRef("pk")),
                ),
            )
        )
        action = getattr(self, 'action', None)
        if action in {'list', 'retrieve', 'partial_update', 'related'}:
            queryset = queryset.prefetch_related(
                Prefetch(
                    "participants",
                    queryset=(
                        EventParticipant.objects
                        .filter(
                            contact__is_active=True,
                            contact__user=self.request.user,
                        )
                        .select_related(
                            "contact",
                            "contact__relation",
                            "contact__occupation",
                            "contact__profile_picture",
                            "contact__profile_picture__media_type",
                        )
                        .order_by("id")
                    ),
                )
            )
        if action in {'retrieve', 'partial_update'}:
            chapter_participants = (
                EventChapterParticipant.objects.filter(
                    contact__is_active=True,
                    contact__user=self.request.user,
                )
                .select_related(
                    "contact",
                    "contact__relation",
                    "contact__occupation",
                    "contact__profile_picture",
                    "contact__profile_picture__media_type",
                )
                .order_by("display_order", "id")
            )
            chapters = (
                EventChapter.objects.select_related("event", "event__user")
                .prefetch_related(
                    Prefetch(
                        "participant_links",
                        queryset=chapter_participants,
                    ),
                )
                .order_by("position", "id")
            )
            queryset = queryset.prefetch_related(
                Prefetch(
                    "chapters",
                    queryset=chapters,
                    to_attr="chapter_headers",
                ),
                Prefetch(
                    "media_attachments",
                    queryset=ready_event_media_queryset(),
                    to_attr="ready_event_media",
                ),
            )
        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"], url_path="related")
    def related(self, request, pk=None):
        event = self._related_base_event(pk)
        limit = self._related_limit(request)
        queryset = self._related_queryset(event)[:limit]
        related_events = list(queryset)

        for related_event in related_events:
            related_event.relation_reasons = self._relation_reasons(related_event)

        serializer = EventRelatedSerializer(
            related_events,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

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

    def _related_limit(self, request):
        raw_limit = request.query_params.get(
            "limit",
            RELATED_EVENTS_DEFAULT_LIMIT,
        )
        try:
            requested_limit = int(raw_limit)
        except (TypeError, ValueError):
            requested_limit = RELATED_EVENTS_DEFAULT_LIMIT
        return min(max(requested_limit, 1), RELATED_EVENTS_MAX_LIMIT)

    def _related_base_event(self, pk):
        event = get_object_or_404(
            Event.objects
            .filter(user=self.request.user)
            .select_related("user", "context_category", "interaction_mode", "mood")
            .prefetch_related(
                Prefetch(
                    "participants",
                    queryset=EventParticipant.objects.filter(
                        contact__is_active=True,
                        contact__user=self.request.user,
                    ),
                )
            ),
            pk=pk,
        )
        self.check_object_permissions(self.request, event)
        return event

    def _related_queryset(self, event):
        base_participant_ids = [
            participant.contact_id for participant in event.participants.all()
        ]
        shared_participant_match = self._shared_participant_match(base_participant_ids)
        queryset = (
            self.get_queryset()
            .exclude(pk=event.pk)
            .annotate(related_shared_participant=shared_participant_match)
            .annotate(
                related_shared_participant_score=Case(
                    When(
                        related_shared_participant=True,
                        then=Value(
                            RELATED_EVENT_REASON_WEIGHTS["shared_participant"],
                        ),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                related_same_context_score=self._field_match_score(
                    "context_category_id",
                    event.context_category_id,
                    RELATED_EVENT_REASON_WEIGHTS["same_context"],
                ),
                related_same_interaction_mode_score=self._field_match_score(
                    "interaction_mode_id",
                    event.interaction_mode_id,
                    RELATED_EVENT_REASON_WEIGHTS["same_interaction_mode"],
                ),
                related_same_tier_score=self._field_match_score(
                    "tier",
                    event.tier,
                    RELATED_EVENT_REASON_WEIGHTS["same_tier"],
                ),
                related_is_upcoming=Case(
                    When(event_timestamp__gt=timezone.now(), then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .annotate(
                related_score=(
                    F("related_shared_participant_score")
                    + F("related_same_context_score")
                    + F("related_same_interaction_mode_score")
                    + F("related_same_tier_score")
                )
            )
            .filter(related_score__gt=0)
            .order_by(
                "related_is_upcoming",
                "-related_score",
                "-event_timestamp",
                "-id",
            )
        )
        return queryset

    def _shared_participant_match(self, participant_ids):
        if not participant_ids:
            return Value(False, output_field=BooleanField())
        return Exists(
            EventParticipant.objects.filter(
                event_id=OuterRef("pk"),
                contact_id__in=participant_ids,
            )
        )

    def _field_match_score(self, field_name, value, weight):
        if value is None:
            return Value(0, output_field=IntegerField())
        return Case(
            When(**{field_name: value}, then=Value(weight)),
            default=Value(0),
            output_field=IntegerField(),
        )

    def _relation_reasons(self, event):
        return [
            reason
            for reason, score_field in sorted(
                RELATED_EVENT_REASON_SCORE_FIELDS,
                key=lambda item: RELATED_EVENT_REASON_WEIGHTS[item[0]],
                reverse=True,
            )
            if getattr(event, score_field, 0)
        ]
