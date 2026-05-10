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
    title = django_filters.CharFilter(field_name='title', lookup_expr='icontains')
    tags = django_filters.NumberFilter(field_name='tags__id')

    class Meta:
        model = Log
        fields = ['event', 'title', 'mood', 'tags', 'created_after', 'created_before']


class ReflectionFilter(JournalTimestampFilterSet):
    title = django_filters.CharFilter(field_name='title', lookup_expr='icontains')

    class Meta:
        model = Reflection
        fields = ['event', 'title', 'subtype', 'created_after', 'created_before']


class ExerciseFilter(JournalTimestampFilterSet):
    title = django_filters.CharFilter(field_name='title', lookup_expr='icontains')

    class Meta:
        model = Exercise
        fields = ['event', 'title', 'subtype', 'created_after', 'created_before']
