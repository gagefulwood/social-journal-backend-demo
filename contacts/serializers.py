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

    class Meta:
        model = Contact
        fields = [
            'id', 'first_name', 'last_name', 'email',
            'phone_number', 'profile_picture',
            'interaction_frequency_score', 'relationship_trend',
            'connection_strength',
        ]

class ContactSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Contact.
    Used by ContactViewSet for POST, PATCH, DELETE, and GET /api/contacts/{id}/
    user is set automatically from request.user in the ViewSet never request body.
    '''
    profile_picture = MediaAssetListSerializer(read_only=True)
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
            'occupation', 'custom_occupation', 'company',
            'education_level', 'custom_education_level', 'school',
            'profile_picture', 'profile_picture_id',
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

    def validate(self, attrs):
        profile_picture = attrs.get('profile_picture')
        if 'profile_picture' in attrs:
            self._validate_profile_picture(profile_picture)
        return attrs

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
