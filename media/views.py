from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from core.pagination import StandardResultsPagination
from core.permissions import IsOwner

from .filters import MediaAssetFilter
from .models import MediaAsset
from .serializers import MediaAssetListSerializer, MediaAssetSerializer


class MediaAssetViewSet(viewsets.ModelViewSet):
    '''
    GET /api/media/ - list active media assets for the current user
    POST /api/media/ - upload a media asset with multipart form data
    GET /api/media/{id}/ - retrieve one media asset
    PATCH /api/media/{id}/ - update media metadata
    DELETE /api/media/{id}/ - soft-delete the media asset row

    Permission: IsAuthenticated, IsOwner
    '''
    permission_classes = [IsAuthenticated, IsOwner]
    pagination_class = StandardResultsPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MediaAssetFilter
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return MediaAsset.objects.none()
        return MediaAsset.objects.for_user(self.request.user).select_related(
            'media_type',
            'user',
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return MediaAssetListSerializer
        return MediaAssetSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_timestamp'])
