import django_filters
from django.db.models import Q
from .models import Contact, Observation

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
        fields = ['occupation']

class ObservationFilter(django_filters.FilterSet):
    '''
    FilterSet for contact observations.
    '''
    class Meta:
        model = Observation
        fields = ['marker', 'is_active']
