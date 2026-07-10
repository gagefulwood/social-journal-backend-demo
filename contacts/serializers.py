from rest_framework import serializers

from events.models import Event, EventParticipant
from lookups.models import FactCategory, ObservationMarker
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
    value = serializers.ReadOnlyField(source='detail_value')
    category_summary = serializers.SerializerMethodField()

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        fields['category'].queryset = (
            FactCategory.objects.for_user(request.user)
            if request and request.user.is_authenticated
            else FactCategory.objects.none()
        )
        return fields

    def get_category_summary(self, obj):
        if obj.category_id is None:
            return None

        parent = obj.category.parent
        return {
            'id': obj.category_id,
            'name': obj.category.name,
            'icon_reference': obj.category.icon_reference,
            'parent': {
                'id': parent.id,
                'name': parent.name,
            } if parent else None,
        }

    class Meta:
        model = Fact
        fields = [
            'id', 'contact', 'category', 'category_summary',
            'detail_value', 'value', 'is_conversation_cue',
        ]
        read_only_fields = ['contact']

class ObservationSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Observation.
    Used by ObservationViewSet nested under /api/contacts/{id}/observations/
    contact_id is set automatically from the URL kwarg in the ViewSet
    '''
    event_summary = serializers.SerializerMethodField()

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        fields['marker'].queryset = (
            ObservationMarker.objects.for_user(request.user)
            if request and request.user.is_authenticated
            else ObservationMarker.objects.none()
        )
        fields['event'].queryset = (
            Event.objects.filter(user=request.user)
            if request and request.user.is_authenticated
            else Event.objects.none()
        )
        return fields

    def validate(self, attrs):
        event = attrs.get('event')
        if event is None:
            return attrs

        contact = self.context.get('contact')
        if contact is None and self.instance is not None:
            contact = self.instance.contact
        if contact is None or not EventParticipant.objects.filter(
            event=event,
            contact=contact,
        ).exists():
            raise serializers.ValidationError({
                'event': 'Select an event shared with this contact.'
            })
        return attrs

    def get_event_summary(self, obj):
        if obj.event_id is None:
            return None
        return {
            'id': obj.event_id,
            'title': obj.event.title,
            'event_timestamp': obj.event.event_timestamp,
        }

    class Meta:
        model = Observation
        fields = [
            'id', 'contact', 'marker', 'body', 'event', 'event_summary',
            'observation_type', 'status', 'occurred_at', 'created_timestamp',
            'archived_at', 'is_active',
        ]
        read_only_fields = [
            'contact', 'created_timestamp', 'archived_at', 'is_active',
        ]

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
