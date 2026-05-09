import django_filters

from .models import MediaAsset


class MediaAssetFilter(django_filters.FilterSet):
    created_after = django_filters.DateTimeFilter(
        field_name='created_timestamp',
        lookup_expr='gte',
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_timestamp',
        lookup_expr='lte',
    )

    class Meta:
        model = MediaAsset
        fields = ['media_type', 'content_type', 'created_after', 'created_before']
