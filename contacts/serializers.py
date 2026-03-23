from rest_framework import serializers
from .models import Contact, ContactPersonalDetail, ContactLooseNote
from lookups.models import ClosenessScore, Occupation, EducationLevel, NoteMarker

class ClosenessScoreSerializer(serializers.ModelSerializer):
    '''
    read-only serializer for Closeness Score lookup
    Nested inside ContactSerializer and ContactListSerializer
    '''
    class Meta:
        model = ClosenessScore
        fields = ['id', 'name']

class ContactPersonalDetailSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for ContactPersonalDetail
    Used by ContactPersonalDetailViewSet nested under:
    /api/contacts/{id}/details/
    contact_id is set automatically from the URL kwarg in the ViewSet
    '''
    class Meta:
        model = ContactPersonalDetail
        fields = ['id', 'contact', 'category', 'detail_value']
        read_only_fields = ['contact']

class ContactLooseNoteSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for ContactLooseNote
    Used by ContactLooseNoteViewSet nested under /api/contacts/{id}/notes/
    contact_id is set automatically from the URL kwarg in the ViewSet
    '''
    class Meta:
        model = ContactLooseNote
        fields = ['id', 'contact', 'marker', 'body', 'created_timestamp', 'is_active']
        read_only_fields = ['contact', 'created_timestamp']

class ContactListSerializer(serializers.ModelSerializer):
    '''
    Serializer for the contacts lists view
    Returns only fields needed for the ContactCard component on frontend
    Avoids heavy joins - closeness_score is the only nested field
    Used by ContactVIewSet for GET /api/contacts/
    '''
    closeness_score = ClosenessScoreSerializer(read_only=True)

    class Meta:
        model = Contact
        fields = [
            'id', 'first_name', 'last_name', 'email',
            'phone_number', 'trust_score', 'closeness_score',
        ]

class ContactSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Contact.
    Used by ContactViewSet for POST, PATCH, DELETE, and GET /api/contacts/{id}/
    user is set automatically from request.user in the ViewSet never request body.
    closeness_score is read_only and never set manually
    '''
    closeness_score = ClosenessScoreSerializer(read_only=True)

    class Meta:
        model = Contact
        fields = [
            'id', 'user', 'first_name', 'middle_name', 'last_name',
            'email', 'phone_mumber', 'address', 'birthday', 'first_met_date',
            'occupation', 'custom_occupation', 'company',
            'education_level', 'custom_education_level', 'school',
            'trust_score', 'cloesness_score',
        ]
        read_only_fields = ['user', 'closeness_score']