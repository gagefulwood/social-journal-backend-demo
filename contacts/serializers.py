from rest_framework import serializers

from media.models import MediaAsset
from media.serializers import MediaAssetListSerializer

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
    profile_picture = MediaAssetListSerializer(read_only=True)
    relation_name = serializers.SerializerMethodField()
    occupation_name = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = [
            'id', 'first_name', 'last_name', 'email',
            'phone_number', 'relation', 'relation_name',
            'occupation', 'occupation_name', 'profile_picture',
            'interaction_frequency_score', 'relationship_trend',
            'connection_strength',
        ]

    def get_relation_name(self, obj):
        return obj.relation.name if obj.relation else None

    def get_occupation_name(self, obj):
        return obj.occupation.name if obj.occupation else None

class ContactSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Contact.
    Used by ContactViewSet for POST, PATCH, DELETE, and GET /api/contacts/{id}/
    user is set automatically from request.user in the ViewSet never request body.
    '''
    profile_picture = MediaAssetListSerializer(read_only=True)
    relation_name = serializers.SerializerMethodField()
    occupation_name = serializers.SerializerMethodField()
    profile_picture_id = serializers.PrimaryKeyRelatedField(
        queryset=MediaAsset.objects.all(),
        source='profile_picture',
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Contact
        fields = [
            'id', 'user', 'first_name', 'middle_name', 'last_name',
            'email', 'phone_number', 'address', 'birthday', 'first_met_date',
            'relation', 'relation_name',
            'occupation', 'occupation_name', 'custom_occupation', 'company',
            'education_level', 'custom_education_level', 'school',
            'profile_picture', 'profile_picture_id',
            'interaction_frequency_score',
            'relationship_trend', 'interaction_diversity_score',
            'sentiment_profile', 'connection_strength',
        ]
        read_only_fields = [
            'user',
            'relation_name',
            'occupation_name',
            'interaction_frequency_score',
            'relationship_trend',
            'interaction_diversity_score',
            'sentiment_profile',
            'connection_strength',
        ]

    def validate(self, attrs):
        if 'relation' in attrs:
            self._validate_relation(attrs.get('relation'))
        profile_picture = attrs.get('profile_picture')
        if 'profile_picture' in attrs:
            self._validate_profile_picture(profile_picture)
        return attrs

    def get_relation_name(self, obj):
        return obj.relation.name if obj.relation else None

    def get_occupation_name(self, obj):
        return obj.occupation.name if obj.occupation else None

    def _validate_relation(self, relation):
        if relation is None:
            return relation

        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError(
                'Select a relation visible to the requesting user.'
            )
        if not relation.is_system_default and relation.user_id != request.user.id:
            raise serializers.ValidationError(
                'Select a relation visible to the requesting user.'
            )
        return relation

    def _validate_profile_picture(self, profile_picture):
        if profile_picture is None:
            return profile_picture

        request = self.context.get('request')
        if not request or profile_picture.user_id != request.user.id:
            raise serializers.ValidationError(
                'Select a profile picture owned by the requesting user.'
            )
        if not profile_picture.is_active:
            raise serializers.ValidationError('Select an active media asset.')
        if not profile_picture.content_type.startswith('image/'):
            raise serializers.ValidationError('Profile pictures must be image uploads.')
        return profile_picture
