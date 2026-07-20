import django_filters
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError as APIValidationError

from journals.models import Log, Reflection

from .models import Event, EventParticipant

PARTICIPANT_ID_FILTER_ERROR = (
    'Participant IDs must be comma-separated valid positive integers.'
)


class EventFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(field_name='title', lookup_expr='icontains')
    search = django_filters.CharFilter(method='filter_search')
    event_after = django_filters.CharFilter(method='filter_event_after')
    event_before = django_filters.CharFilter(method='filter_event_before')
    participants = django_filters.CharFilter(method='filter_participants')
    journaled = django_filters.BooleanFilter(method='filter_journaled')
    has_mood = django_filters.BooleanFilter(method='filter_has_mood')
    ordering = django_filters.ChoiceFilter(
        choices=(
            ('event_timestamp', 'Event timestamp (oldest first)'),
            ('-event_timestamp', 'Event timestamp (newest first)'),
        ),
        method='filter_ordering',
    )

    class Meta:
        model = Event
        fields = [
            'event_after',
            'event_before',
            'title',
            'search',
            'tier',
            'impact',
            'context_category',
            'interaction_mode',
            'participants',
            'journaled',
            'has_mood',
            'ordering',
        ]

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        participant_scope = Q(
            participants__contact__user=self.request.user,
            participants__contact__is_active=True,
        )
        return queryset.filter(
            Q(title__icontains=value)
            | Q(description__icontains=value)
            | Q(location_label__icontains=value)
            | Q(context_category__name__icontains=value)
            | Q(interaction_mode__name__icontains=value)
            | (participant_scope & Q(participants__contact__first_name__icontains=value))
            | (participant_scope & Q(participants__contact__last_name__icontains=value))
            | (participant_scope & Q(participants__contact__email__icontains=value))
        ).distinct()

    def filter_event_after(self, queryset, name, value):
        parsed_value = self._parse_datetime_value(value)
        if parsed_value is None:
            return queryset
        return queryset.filter(event_timestamp__gte=parsed_value)

    def filter_event_before(self, queryset, name, value):
        parsed_value = self._parse_datetime_value(value)
        if parsed_value is None:
            return queryset
        return queryset.filter(event_timestamp__lte=parsed_value)

    def filter_participants(self, queryset, name, value):
        contact_id_field = EventParticipant._meta.get_field('contact').target_field
        contact_ids = []
        for raw_contact_id in value.split(','):
            raw_contact_id = raw_contact_id.strip()
            if not raw_contact_id:
                continue
            try:
                contact_id = contact_id_field.clean(raw_contact_id, None)
            except (DjangoValidationError, TypeError, ValueError):
                raise APIValidationError({
                    name: [PARTICIPANT_ID_FILTER_ERROR],
                }) from None
            if contact_id <= 0:
                raise APIValidationError({
                    name: [PARTICIPANT_ID_FILTER_ERROR],
                })
            contact_ids.append(contact_id)
        if not contact_ids:
            return queryset
        return queryset.filter(
            participants__contact_id__in=contact_ids,
            participants__contact__user=self.request.user,
            participants__contact__is_active=True,
        ).distinct()

    def filter_journaled(self, queryset, name, value):
        queryset = queryset.annotate(
            has_log=Exists(Log.objects.filter(event_id=OuterRef('pk'))),
            has_reflection=Exists(Reflection.objects.filter(event_id=OuterRef('pk'))),
        )
        if value:
            return queryset.filter(Q(has_log=True) | Q(has_reflection=True))
        return queryset.filter(
            has_log=False,
            has_reflection=False,
        )

    def filter_has_mood(self, queryset, name, value):
        if value:
            return queryset.filter(mood__isnull=False)
        return queryset.filter(mood__isnull=True)

    def filter_ordering(self, queryset, name, value):
        if value == 'event_timestamp':
            return queryset.order_by('event_timestamp', 'id')
        if value == '-event_timestamp':
            return queryset.order_by('-event_timestamp', '-id')
        return queryset

    def _parse_datetime_value(self, value):
        if value == 'now':
            return timezone.now()
        return parse_datetime(value)
