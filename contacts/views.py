from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404

from .models import Contact, Fact, Observation
from .serializers import (
    ContactSerializer,
    ContactListSerializer,
    FactSerializer,
    ObservationSerializer,
)
from .filters import ContactFilter, FactFilter, ObservationFilter
from core.permissions import IsOwner
from core.pagination import StandardResultsPagination

class ContactViewSet(viewsets.ModelViewSet):
    '''
    GET /api/contacts/
    POST /api/contacts/
    GET /api/contacts/{id}/
    PATCH /api/contacts/{id}/
    DELETE /api/contracts/{id}/
    '''
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ContactFilter
    pagination_class = StandardResultsPagination
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Contact.objects.none()
        queryset = Contact.objects.for_user(self.request.user)
        if self.action != 'list':
            queryset = queryset.prefetch_related(
                'contact_methods', 'addresses', 'employment', 'education',
            )
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ContactListSerializer
        return ContactSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class NestedContactContextViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_contact(self):
        if not hasattr(self, '_contact'):
            self._contact = get_object_or_404(
                Contact.objects.for_user(self.request.user),
                pk=self.kwargs['contact_pk'],
            )
        return self._contact

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, 'swagger_fake_view', False):
            context['contact'] = self.get_contact()
        return context


class PinnableContextViewSetMixin:
    @extend_schema(request=None)
    @action(detail=True, methods=['post'])
    def pin(self, request, *args, **kwargs):
        instance = self.get_object().pin()
        return Response(self.get_serializer(instance).data)

    @extend_schema(request=None)
    @action(detail=True, methods=['post'])
    def unpin(self, request, *args, **kwargs):
        instance = self.get_object().unpin()
        return Response(self.get_serializer(instance).data)


class FactViewSet(PinnableContextViewSetMixin, NestedContactContextViewSet):
    '''
    GET /api/contacts/{contact_id}/facts/
    POST /api/contacts/{contact_id}/facts/
    PATCH /api/contacts/{contact_id}/facts/{id}/
    DELETE /api/contacts/{contact_id}/facts/{id}/
    '''
    serializer_class = FactSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = FactFilter

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Fact.objects.none()
        return Fact.objects.filter(
            contact=self.get_contact()
        ).select_related(
            'category',
            'category__parent',
        ).order_by('id')
    
    def perform_create(self, serializer):
        serializer.save(contact=self.get_contact())

class ObservationViewSet(PinnableContextViewSetMixin, NestedContactContextViewSet):
    '''
    GET /api/contacts/{contact_id}/observations/
    POST /api/contacts/{contact_id}/observations/
    PATCH /api/contacts/{contact_id}/observations/{id}/
    DELETE /api/contacts/{contact_id}/observations/{id}/
    '''
    serializer_class = ObservationSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ObservationFilter

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Observation.objects.none()
        queryset = Observation.objects.for_user(self.request.user).filter(
            contact=self.get_contact()
        ).select_related(
            'marker',
            'event',
        )
        if (
            self.action == 'list'
            and not self.request.query_params.get('status')
            and 'is_active' not in self.request.query_params
        ):
            queryset = queryset.exclude(status='archived')
        return queryset.annotate(
            meaningful_timestamp=Coalesce('occurred_at', 'created_timestamp')
        ).order_by(
            '-meaningful_timestamp',
            '-pk',
        )
    
    def perform_create(self, serializer):
        serializer.save(contact=self.get_contact())
