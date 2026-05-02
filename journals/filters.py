import django_filters

from .models import Exercise, Log, Reflection


class JournalTimestampFilterSet(django_filters.FilterSet):
    created_after = django_filters.DateTimeFilter(
        field_name='created_timestamp',
        lookup_expr='gte',
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_timestamp',
        lookup_expr='lte',
    )


class LogFilter(JournalTimestampFilterSet):
    tags = django_filters.NumberFilter(field_name='tags__id')

    class Meta:
        model = Log
        fields = ['event', 'mood', 'tags', 'created_after', 'created_before']


class ReflectionFilter(JournalTimestampFilterSet):
    class Meta:
        model = Reflection
        fields = ['event', 'subtype', 'created_after', 'created_before']


class ExerciseFilter(JournalTimestampFilterSet):
    class Meta:
        model = Exercise
        fields = ['event', 'subtype', 'created_after', 'created_before']
