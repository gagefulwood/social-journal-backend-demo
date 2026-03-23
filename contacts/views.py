from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Contact, ContactPersonalDetail, ContactLooseNote
from .serializers import (
    ContactSerializer,
    ContactListSerializer,
    ContactPersonalDetailSerializer,
    ContactLooseNoteSerializer,
)
from .filters import ContactFilter
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
        return Contact.objects.for_user(self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ContactListSerializer
        return ContactSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class ContactPersonalDetailViewSet(viewsets.ModelViewSet):
    '''
    GET /api/contacts/{contact_id}/details/
    POST /api/contacts/{contact_id}/details/
    PATCH /api/contacts/{contact_id}/details/{id}/
    DELETE /api/contacts/{cotact_id}/details/{id}/
    '''
    serializer_class = ContactPersonalDetailSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return ContactPersonalDetail.objects.filter(
            contact_id=self.kwargs['contact_pk'],
            contact__user=self.request.user
        )
    
    def perform_create(self, serializer):
        contact = Contact.objects.get(
            pk=self.kwargs['contacts_pk'],
            user=self.request.user
        )
        serializer.save(contact=contact)

class ContactLooseNoteViewSet(viewsets.ModelViewSet):
    '''
    GET /api/contacts/{contact_id}/notes/
    POST /api/contacts/{contact_id}/notes/
    PATCH /api/contacts/{contac_id}/notes/{id}/
    DELETE /api/contacts/{contact_id}/notes/{id}/
    '''
    serializer_class = ContactLooseNoteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return ContactLooseNote.objects.filter(
            contact_id=self.kwargs['contact_pk'],
            contact__user=self.request.user,
        )
    
    def perform_create(self, serializer):
        contact = Contact.objects.get(
            pk=self.kwargs['contact_pk'],
            user=self.request.user,
        )
        serializer.save(contact=contact)