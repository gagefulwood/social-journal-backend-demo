import django_filters
from .models import JournalEntry

class JournalEntryFilter(django_filters.FilterSet):
    event_id = django_filters.UUIDFilter(field_name='event_id')
    mood_id = django_filters.NumberFilter(field_name='mood_id')
    entry_timestamp_after = django_filters.DateTimeFilter(field_name='entry_timestamp', lookup_expr='gte')
    entry_timestamp_before = django_filters.DateTimeFilter(field_name='entry_timestamp', lookup_expr='lte')

    class Meta:
        model = JournalEntry
        fields = ['event_id', 'mood_id', 'entry_timestamp_after', 'entry_timestamp_before']