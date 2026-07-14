import re
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from rest_framework import serializers

from events.models import Event, EventParticipant
from lookups.models import FactCategory, ObservationMarker
from media.models import MediaAsset
from media.serializers import MediaAssetListSerializer

from .models import (
    Contact,
    ContactAddress,
    ContactEducation,
    ContactEmployment,
    ContactMethod,
    Fact,
    Observation,
)


PHONE_PATTERN = re.compile(r'^\+?[0-9().\- xX]{7,32}$')


def validate_phone_value(value):
    value = value.strip()
    if not PHONE_PATTERN.fullmatch(value) or len(re.sub(r'\D', '', value)) < 7:
        raise serializers.ValidationError('Enter a valid phone number.')
    return value


class ContactMethodSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ContactMethod
        fields = ['id', 'kind', 'label', 'value', 'is_primary']

    def validate(self, attrs):
        if attrs.get('kind') == ContactMethod.KIND_EMAIL:
            serializers.EmailField().run_validation(attrs.get('value'))
        elif attrs.get('kind') == ContactMethod.KIND_PHONE:
            attrs['value'] = validate_phone_value(attrs.get('value', ''))
        return attrs


class ContactAddressSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ContactAddress
        fields = [
            'id', 'label', 'line_1', 'line_2', 'city', 'region',
            'postal_code', 'country_code', 'is_primary',
        ]

    def validate_country_code(self, value):
        value = value.strip().upper()
        if value and (len(value) != 2 or not value.isalpha()):
            raise serializers.ValidationError('Use a two-letter country code.')
        return value


class DateRangeSerializerMixin:
    def validate(self, attrs):
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be on or after start date.'
            })
        if attrs.get('is_current') and end_date:
            raise serializers.ValidationError({
                'end_date': 'A current entry cannot have an end date.'
            })
        return attrs


class ContactEmploymentSerializer(DateRangeSerializerMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ContactEmployment
        fields = [
            'id', 'title', 'organization', 'start_date', 'end_date',
            'is_current',
        ]


class ContactEducationSerializer(DateRangeSerializerMixin, serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ContactEducation
        fields = [
            'id', 'credential', 'field_of_study', 'institution',
            'start_date', 'end_date', 'is_current',
        ]

class FactSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Fact.
    Used by FactViewSet nested under:
    /api/contacts/{id}/facts/
    contact_id is set automatically from the URL kwarg in the ViewSet
    '''
    value = serializers.ReadOnlyField(source='detail_value')
    category_summary = serializers.SerializerMethodField()
    is_pinned = serializers.BooleanField(read_only=True)

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
            'label', 'detail_value', 'value', 'is_conversation_cue',
            'is_pinned', 'pinned_at',
        ]
        read_only_fields = ['contact', 'pinned_at']

class ObservationSerializer(serializers.ModelSerializer):
    '''
    Full CRUD serializer for Observation.
    Used by ObservationViewSet nested under /api/contacts/{id}/observations/
    contact_id is set automatically from the URL kwarg in the ViewSet
    '''
    event_summary = serializers.SerializerMethodField()
    is_pinned = serializers.BooleanField(read_only=True)

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
            'archived_at', 'is_active', 'is_pinned', 'pinned_at',
        ]
        read_only_fields = [
            'contact', 'created_timestamp', 'archived_at', 'is_active',
            'pinned_at',
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
    birth_date = serializers.DateField(
        source='birthday', required=False, allow_null=True,
    )
    first_met_on = serializers.DateField(
        source='first_met_date', required=False, allow_null=True,
    )
    age = serializers.SerializerMethodField()
    contact_methods = ContactMethodSerializer(many=True, required=False)
    addresses = ContactAddressSerializer(many=True, required=False)
    employment = ContactEmploymentSerializer(many=True, required=False)
    education = ContactEducationSerializer(many=True, required=False)
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
            'preferred_name', 'gender_identity', 'pronouns', 'birth_date',
            'age', 'timezone', 'first_met_on', 'met_through', 'met_location',
            'contact_methods', 'addresses', 'employment', 'education',
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
            'age',
        ]

    def validate(self, attrs):
        self._validate_profile_aliases()
        self._validate_timezone(attrs.get('timezone'))
        self._validate_nested_primary_records(attrs)
        if 'relation' in attrs:
            self._validate_relation(attrs.get('relation'))
        profile_picture = attrs.get('profile_picture')
        if 'profile_picture' in attrs:
            self._validate_profile_picture(profile_picture)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        nested = self._pop_nested(validated_data)
        contact = super().create(validated_data)
        self._sync_nested(contact, nested)
        return contact

    @transaction.atomic
    def update(self, instance, validated_data):
        nested = self._pop_nested(validated_data)
        contact = super().update(instance, validated_data)
        self._sync_nested(contact, nested)
        return contact

    def get_age(self, obj):
        if obj.birthday is None:
            return None
        today = date.today()
        return today.year - obj.birthday.year - (
            (today.month, today.day) < (obj.birthday.month, obj.birthday.day)
        )

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

    def _validate_profile_aliases(self):
        data = self.initial_data
        if 'age' in data:
            raise serializers.ValidationError({'age': 'Age is read-only.'})
        alias_pairs = [
            ('birth_date', 'birthday'),
            ('first_met_on', 'first_met_date'),
        ]
        for canonical, legacy in alias_pairs:
            if canonical in data and legacy in data and data[canonical] != data[legacy]:
                raise serializers.ValidationError({
                    canonical: f'Does not match {legacy}.'
                })

    def _validate_timezone(self, value):
        if not value:
            return
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise serializers.ValidationError({
                'timezone': 'Enter a valid IANA time zone.'
            })

    def _validate_nested_primary_records(self, attrs):
        methods = attrs.get('contact_methods')
        if methods is not None:
            primary_kinds = [item['kind'] for item in methods if item.get('is_primary')]
            duplicates = {kind for kind in primary_kinds if primary_kinds.count(kind) > 1}
            if duplicates:
                raise serializers.ValidationError({
                    'contact_methods': 'Only one primary method is allowed per kind.'
                })
        addresses = attrs.get('addresses')
        if addresses is not None and sum(
            bool(item.get('is_primary')) for item in addresses
        ) > 1:
            raise serializers.ValidationError({
                'addresses': 'Only one primary address is allowed.'
            })

    @staticmethod
    def _pop_nested(validated_data):
        missing = object()
        nested = {}
        for field in ('contact_methods', 'addresses', 'employment', 'education'):
            value = validated_data.pop(field, missing)
            if value is not missing:
                nested[field] = value
        return nested

    def _sync_nested(self, contact, nested):
        configs = {
            'contact_methods': (ContactMethod, ContactMethodSerializer),
            'addresses': (ContactAddress, ContactAddressSerializer),
            'employment': (ContactEmployment, ContactEmploymentSerializer),
            'education': (ContactEducation, ContactEducationSerializer),
        }
        for field, items in nested.items():
            model, serializer_class = configs[field]
            manager = getattr(contact, field)
            existing = {item.pk: item for item in manager.select_for_update()}
            if field in {'contact_methods', 'addresses'}:
                manager.filter(is_primary=True).update(is_primary=False)
                for instance in existing.values():
                    instance.is_primary = False
            retained_ids = set()
            for item_data in items:
                item_id = item_data.pop('id', None)
                if item_id is None:
                    model.objects.create(contact=contact, **item_data)
                    continue
                instance = existing.get(item_id)
                if instance is None:
                    raise serializers.ValidationError({
                        field: f'Item {item_id} does not belong to this contact.'
                    })
                item_serializer = serializer_class(
                    instance,
                    data=item_data,
                    partial=False,
                    context=self.context,
                )
                item_serializer.is_valid(raise_exception=True)
                item_serializer.save()
                retained_ids.add(item_id)
            manager.exclude(pk__in=retained_ids).filter(pk__in=existing).delete()
            getattr(contact, '_prefetched_objects_cache', {}).pop(field, None)
