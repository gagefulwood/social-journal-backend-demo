import django_filters
from django.db.models import F, Q
from .models import Contact, Fact, Observation


class PinnableContextFilterSet(django_filters.FilterSet):
    pinned = django_filters.BooleanFilter(method='filter_pinned')
    ordering = django_filters.ChoiceFilter(
        choices=(
            ('pinned_at', 'Pinned timestamp (oldest first)'),
            ('-pinned_at', 'Pinned timestamp (newest first)'),
        ),
        method='filter_ordering',
    )

    def filter_pinned(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(pinned_at__isnull=not value)

    def filter_ordering(self, queryset, name, value):
        if value == 'pinned_at':
            return queryset.order_by(
                F('pinned_at').asc(nulls_last=True),
                'id',
            )
        if value == '-pinned_at':
            return queryset.order_by(
                F('pinned_at').desc(nulls_last=True),
                '-id',
            )
        return queryset

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

class ObservationFilter(PinnableContextFilterSet):
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
        fields = [
            'status',
            'observation_type',
            'marker',
            'event',
            'pinned',
            'ordering',
        ]


class FactFilter(PinnableContextFilterSet):
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Fact
        fields = [
            'category',
            'is_conversation_cue',
            'pinned',
            'ordering',
        ]

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(label__icontains=value)
            | Q(detail_value__icontains=value)
            | Q(category__name__icontains=value)
        )
