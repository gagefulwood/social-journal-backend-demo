from rest_framework import serializers
from .models import Event, EventParticipant
from contacts.models import Contact
from contacts.serializers import ContactListSerializer
from lookups.serializers import ContextCategorySerializer

class EventParticipantSerializer(serializers.ModelSerializer):
    contact = ContactListSerializer(read_only=True)

    class Meta:
        model = EventParticipant
        fields = ['id', 'contact']

class EventSerializer(serializers.ModelSerializer):
    '''
    Full serializer for Event create and list.
    participant_ids: write-only list of contact PKs submitted on event creation.
    participants: read-only nested contact summaries returned in responses.
    user is set automatically from request.user in the ViewSet.
    '''
    participant_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        write_only=True,
        queryset=Contact.objects.all(),
        source='participant_contacts',
        required=False,
    )
    participants = EventParticipantSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Event
        fields = [
            'id', 'user', 'title', 'event_timestamp',
            'context_category', 'participant_ids', 'participants',
            'journaled',
        ]
        read_only_fields = ['user', 'participants', 'journaled']

    def create(self, validated_data):
        participant_contacts = validated_data.pop('participant_contacts', [])
        event = Event.objects.create(**validated_data)

        for contact in participant_contacts:
            EventParticipant.objects.create(event=event, contact=contact)
        return event

class EventListSerializer(serializers.ModelSerializer):
    """Lightweight serializer used on GET /api/events/ list view."""
    context_category = ContextCategorySerializer(read_only=True)
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "event_timestamp",
            "context_category",
            "participant_count",
            "journaled",
        ]

    def get_participant_count(self, obj):
        return obj.participants.count()
