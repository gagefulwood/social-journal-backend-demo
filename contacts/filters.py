import django_filters
from django.db.models import Q
from .models import Contact

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
        fields = ['occupation', 'closeness_score']