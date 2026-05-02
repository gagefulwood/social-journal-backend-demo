from rest_framework import serializers
from .models import Contact, Fact, Observation

class FactSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Fact.
    Used by FactViewSet nested under:
    /api/contacts/{id}/facts/
    contact_id is set automatically from the URL kwarg in the ViewSet
    '''
    class Meta:
        model = Fact
        fields = ['id', 'contact', 'category', 'detail_value']
        read_only_fields = ['contact']

class ObservationSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Observation.
    Used by ObservationViewSet nested under /api/contacts/{id}/observations/
    contact_id is set automatically from the URL kwarg in the ViewSet
    '''
    class Meta:
        model = Observation
        fields = ['id', 'contact', 'marker', 'body', 'created_timestamp', 'is_active']
        read_only_fields = ['contact', 'created_timestamp']

class ContactListSerializer(serializers.ModelSerializer):
    '''
    Serializer for the contacts lists view
    Returns only fields needed for the ContactCard component on frontend
    Avoids heavy joins and returns computed relationship card fields.
    Used by ContactVIewSet for GET /api/contacts/
    '''
    class Meta:
        model = Contact
        fields = [
            'id', 'first_name', 'last_name', 'email',
            'phone_number',
            'interaction_frequency_score', 'relationship_trend',
            'connection_strength',
        ]

class ContactSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Contact.
    Used by ContactViewSet for POST, PATCH, DELETE, and GET /api/contacts/{id}/
    user is set automatically from request.user in the ViewSet never request body.
    '''
    class Meta:
        model = Contact
        fields = [
            'id', 'user', 'first_name', 'middle_name', 'last_name',
            'email', 'phone_number', 'address', 'birthday', 'first_met_date',
            'occupation', 'custom_occupation', 'company',
            'education_level', 'custom_education_level', 'school',
            'interaction_frequency_score',
            'relationship_trend', 'interaction_diversity_score',
            'sentiment_profile', 'connection_strength',
        ]
        read_only_fields = [
            'user',
            'interaction_frequency_score',
            'relationship_trend',
            'interaction_diversity_score',
            'sentiment_profile',
            'connection_strength',
        ]
