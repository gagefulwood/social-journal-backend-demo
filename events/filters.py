import django_filters
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from journals.models import Exercise, Log, Reflection

from .models import Event


class EventFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(field_name='title', lookup_expr='icontains')
    search = django_filters.CharFilter(method='filter_search')
    event_after = django_filters.CharFilter(method='filter_event_after')
    event_before = django_filters.CharFilter(method='filter_event_before')
    participants = django_filters.CharFilter(method='filter_participants')
    journaled = django_filters.BooleanFilter(method='filter_journaled')
    has_mood = django_filters.BooleanFilter(method='filter_has_mood')

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
        ]

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(title__icontains=value)
            | Q(description__icontains=value)
            | Q(location_label__icontains=value)
            | Q(context_category__name__icontains=value)
            | Q(interaction_mode__name__icontains=value)
            | Q(participants__contact__first_name__icontains=value)
            | Q(participants__contact__last_name__icontains=value)
            | Q(participants__contact__email__icontains=value)
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
        contact_ids = [
            contact_id.strip()
            for contact_id in value.split(',')
            if contact_id.strip()
        ]
        if not contact_ids:
            return queryset
        return queryset.filter(participants__contact_id__in=contact_ids).distinct()

    def filter_journaled(self, queryset, name, value):
        queryset = queryset.annotate(
            has_log=Exists(Log.objects.filter(event_id=OuterRef('pk'))),
            has_reflection=Exists(Reflection.objects.filter(event_id=OuterRef('pk'))),
            has_exercise=Exists(Exercise.objects.filter(event_id=OuterRef('pk'))),
        )
        if value:
            return queryset.filter(
                Q(has_log=True) | Q(has_reflection=True) | Q(has_exercise=True)
            )
        return queryset.filter(
            has_log=False,
            has_reflection=False,
            has_exercise=False,
        )

    def filter_has_mood(self, queryset, name, value):
        if value:
            return queryset.filter(mood__isnull=False)
        return queryset.filter(mood__isnull=True)

    def _parse_datetime_value(self, value):
        if value == 'now':
            return timezone.now()
        return parse_datetime(value)
