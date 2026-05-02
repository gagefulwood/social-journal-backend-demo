from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Contact, Fact, Observation
from .serializers import (
    ContactSerializer,
    ContactListSerializer,
    FactSerializer,
    ObservationSerializer,
)
from .filters import ContactFilter, ObservationFilter
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
        return Contact.objects.for_user(self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ContactListSerializer
        return ContactSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class FactViewSet(viewsets.ModelViewSet):
    '''
    GET /api/contacts/{contact_id}/facts/
    POST /api/contacts/{contact_id}/facts/
    PATCH /api/contacts/{contact_id}/facts/{id}/
    DELETE /api/contacts/{contact_id}/facts/{id}/
    '''
    serializer_class = FactSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Fact.objects.none()
        return Fact.objects.filter(
            contact_id=self.kwargs['contact_pk'],
            contact__user=self.request.user,
        )
    
    def perform_create(self, serializer):
        contact = Contact.objects.get(
            pk=self.kwargs['contact_pk'],
            user=self.request.user
        )
        serializer.save(contact=contact)

class ObservationViewSet(viewsets.ModelViewSet):
    '''
    GET /api/contacts/{contact_id}/observations/
    POST /api/contacts/{contact_id}/observations/
    PATCH /api/contacts/{contact_id}/observations/{id}/
    DELETE /api/contacts/{contact_id}/observations/{id}/
    '''
    serializer_class = ObservationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ObservationFilter
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Observation.objects.none()
        return Observation.objects.for_user(self.request.user).filter(
            contact_id=self.kwargs['contact_pk']
        )
    
    def perform_create(self, serializer):
        contact = Contact.objects.get(
            pk=self.kwargs['contact_pk'],
            user=self.request.user,
        )
        serializer.save(contact=contact)
