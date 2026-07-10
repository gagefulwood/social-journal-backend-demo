import django_filters
from django.db.models import Q
from .models import Contact, Fact, Observation

class ContactFilter(django_filters.FilterSet):
    '''
    
    '''
    name = django_filters.CharFilter(method='filter_name', label='Name')

    def filter_name(self, queryset, name, value):
        return queryset.filter(
            Q(first_name__icontains=value) | Q(last_name__icontains=value)
        )
    
    class Meta:
        model = Contact
        fields = ['occupation', 'relation']

class ObservationFilter(django_filters.FilterSet):
    '''
    FilterSet for contact observations.
    '''
    search = django_filters.CharFilter(method='filter_search')
    occurred_after = django_filters.IsoDateTimeFilter(
        field_name='occurred_at',
        lookup_expr='gte',
    )
    occurred_before = django_filters.IsoDateTimeFilter(
        field_name='occurred_at',
        lookup_expr='lte',
    )
    created_after = django_filters.IsoDateTimeFilter(
        field_name='created_timestamp',
        lookup_expr='gte',
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name='created_timestamp',
        lookup_expr='lte',
    )
    is_active = django_filters.BooleanFilter(method='filter_is_active')

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(body__icontains=value)

    def filter_is_active(self, queryset, name, value):
        if value:
            return queryset.exclude(status='archived')
        return queryset.filter(status='archived')

    class Meta:
        model = Observation
        fields = ['status', 'observation_type', 'marker', 'event']


class FactFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Fact
        fields = ['category', 'is_conversation_cue']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(detail_value__icontains=value)
            | Q(category__name__icontains=value)
        )
