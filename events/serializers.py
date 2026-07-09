from rest_framework import serializers
from .models import Event, EventParticipant
from contacts.models import Contact
from contacts.serializers import ContactListSerializer
from lookups.models import InteractionMode, Mood
from lookups.serializers import (
    ContextCategorySerializer,
    InteractionModeSerializer,
    MoodSerializer,
)

class EventParticipantSerializer(serializers.ModelSerializer):
    contact = ContactListSerializer(read_only=True)

    class Meta:
        model = EventParticipant
        fields = ['id', 'contact']

class EventSerializer(serializers.ModelSerializer):
    '''
    Full serializer for Event create, retrieve, and update.
    participants accepts a write-only list of contact IDs and renders nested
    participant summaries in responses.
    user is set automatically from request.user in the ViewSet.
    '''
    participants = serializers.PrimaryKeyRelatedField(
        many=True,
        write_only=True,
        queryset=Contact.objects.all(),
        source='participant_contacts',
        required=False,
    )
    interaction_mode = InteractionModeSerializer(read_only=True)
    interaction_mode_id = serializers.PrimaryKeyRelatedField(
        queryset=InteractionMode.objects.all(),
        source='interaction_mode',
        write_only=True,
        required=False,
        allow_null=True,
    )
    mood = MoodSerializer(read_only=True)
    mood_id = serializers.PrimaryKeyRelatedField(
        queryset=Mood.objects.all(),
        source='mood',
        write_only=True,
        required=False,
        allow_null=True,
    )
    journals = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'user', 'title', 'description', 'event_timestamp',
            'end_timestamp', 'location_label', 'tier', 'impact',
            'context_category', 'interaction_mode', 'interaction_mode_id',
            'mood', 'mood_id', 'participants', 'journaled', 'journals',
        ]
        read_only_fields = ['user', 'journaled', 'journals']

    def validate(self, attrs):
        if self.instance and 'event_timestamp' in attrs:
            if attrs['event_timestamp'] != self.instance.event_timestamp:
                raise serializers.ValidationError({
                    'event_timestamp': 'Event timestamp cannot be changed after creation.'
                })
        user = self._request_user()
        if user:
            self._validate_visible_lookup(
                'interaction_mode_id',
                attrs.get('interaction_mode'),
                InteractionMode,
                user,
            )
            self._validate_visible_lookup(
                'mood_id',
                attrs.get('mood'),
                Mood,
                user,
            )
        return attrs

    def create(self, validated_data):
        participant_contacts = validated_data.pop('participant_contacts', [])
        self._validate_participant_contacts(participant_contacts, validated_data['user'])
        self._validate_visible_lookup(
            'interaction_mode_id',
            validated_data.get('interaction_mode'),
            InteractionMode,
            validated_data['user'],
        )
        self._validate_visible_lookup(
            'mood_id',
            validated_data.get('mood'),
            Mood,
            validated_data['user'],
        )
        event = Event.objects.create(**validated_data)

        for contact in self._unique_contacts(participant_contacts):
            EventParticipant.objects.create(event=event, contact=contact)
        return event

    def update(self, instance, validated_data):
        participant_contacts = validated_data.pop('participant_contacts', None)
        if participant_contacts is not None:
            self._validate_participant_contacts(participant_contacts, instance.user)
        self._validate_visible_lookup(
            'interaction_mode_id',
            validated_data.get('interaction_mode'),
            InteractionMode,
            instance.user,
        )
        self._validate_visible_lookup(
            'mood_id',
            validated_data.get('mood'),
            Mood,
            instance.user,
        )
        instance = super().update(instance, validated_data)
        if participant_contacts is not None:
            self._replace_participants(instance, participant_contacts)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['participants'] = EventParticipantSerializer(
            instance.participants.all(),
            many=True,
            context=self.context,
        ).data
        return data

    def get_journals(self, obj):
        return {
            'logs': [self._log_summary(log) for log in obj.logs.all()],
            'reflections': [
                self._reflection_summary(reflection)
                for reflection in obj.reflections.all()
            ],
            'exercises': [
                self._exercise_summary(exercise)
                for exercise in obj.exercises.all()
            ],
        }

    def _log_summary(self, log):
        return {
            'id': log.id,
            'kind': 'log',
            'title': log.title,
            'mood': MoodSerializer(log.mood, context=self.context).data
            if log.mood_id else None,
            'created_timestamp': log.created_timestamp,
            'updated_timestamp': log.updated_timestamp,
        }

    def _reflection_summary(self, reflection):
        return {
            'id': reflection.id,
            'kind': 'reflection',
            'title': reflection.title,
            'subtype': reflection.subtype,
            'clarity_check': reflection.clarity_check,
            'created_timestamp': reflection.created_timestamp,
            'updated_timestamp': reflection.updated_timestamp,
        }

    def _exercise_summary(self, exercise):
        return {
            'id': exercise.id,
            'kind': 'exercise',
            'title': exercise.title,
            'subtype': exercise.subtype,
            'measurement_delta': exercise.measurement_delta,
            'created_timestamp': exercise.created_timestamp,
            'updated_timestamp': exercise.updated_timestamp,
        }

    def _validate_participant_contacts(self, contacts, user):
        invalid_contacts = [contact for contact in contacts if contact.user_id != user.id]
        if invalid_contacts:
            raise serializers.ValidationError({
                'participants': 'Select contacts owned by the requesting user.'
            })

    def _validate_visible_lookup(self, field_name, lookup, model, user):
        if not lookup:
            return
        if not model.objects.for_user(user).filter(pk=lookup.pk).exists():
            raise serializers.ValidationError({
                field_name: 'Select a lookup row visible to the requesting user.'
            })

    def _request_user(self):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            return request.user
        return None

    def _replace_participants(self, event, requested_contacts):
        requested_contacts = self._unique_contacts(requested_contacts)
        requested_ids = {contact.id for contact in requested_contacts}
        existing_participants = {
            participant.contact_id: participant
            for participant in event.participants.all()
        }
        existing_ids = set(existing_participants)

        for contact in requested_contacts:
            if contact.id not in existing_ids:
                EventParticipant.objects.create(event=event, contact=contact)

        for contact_id in existing_ids - requested_ids:
            existing_participants[contact_id].delete()

    def _unique_contacts(self, contacts):
        unique_contacts = []
        seen_ids = set()
        for contact in contacts:
            if contact.id in seen_ids:
                continue
            seen_ids.add(contact.id)
            unique_contacts.append(contact)
        return unique_contacts

class EventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer used on GET /api/events/ list view."""
    context_category = ContextCategorySerializer(read_only=True)
    interaction_mode = InteractionModeSerializer(read_only=True)
    mood = MoodSerializer(read_only=True)
    participants = EventParticipantSerializer(many=True, read_only=True)
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "event_timestamp",
            "end_timestamp",
            "location_label",
            "tier",
            "impact",
            "context_category",
            "interaction_mode",
            "mood",
            "participants",
            "participant_count",
            "journaled",
        ]

    def get_participant_count(self, obj):
        return obj.participants.count()


class EventRelatedSerializer(EventListSerializer):
    """Event list row plus machine-readable reasons for related ranking."""
    relation_reasons = serializers.SerializerMethodField()

    class Meta(EventListSerializer.Meta):
        fields = EventListSerializer.Meta.fields + ["relation_reasons"]

    def get_relation_reasons(self, obj):
        return getattr(obj, "relation_reasons", [])
