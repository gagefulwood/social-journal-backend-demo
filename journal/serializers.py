from rest_framework import serializers
from .models import JournalEntry, Reflection
from lookups.serializers import MoodSerializer, JournalTagSerializer

class JournalEntryListSerializer(serializers.ModelSerializer):
    mood = MoodSerializer(read_only=True)
    tags = JournalTagSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = ['id', 'title', 'entry_timestamp', 'mood', 'tags']

class JournalEntrySerializer(serializers.ModelSerializer):
    event_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    mood = MoodSerializer(read_only=True)
    tags = JournalTagSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = ['id', 'event_id', 'title', 'entry_timestamp', 'mood', 'tags', 'body', 'event','is_immutable']
        read_only_fields = ['event', 'is_immutable']

    def validate_body(self, value):
        '''
        Reject body updates after the entry is marked immutable.
        `is_immutable` is set by the post_save signal following creation.
        '''
        if self.instance and self.instance.is_immutable:
            raise serializers.ValidationError(
                "Journal entry body cannot be edited after creation."
            )
        return value
    
class ReflectionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Reflection
        fields = ['id', 'body', 'created_timestamp', 'journal_entry']
        read_only_fields = ['created_timestamp', 'journal_entry']