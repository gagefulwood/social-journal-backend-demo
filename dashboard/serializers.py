from rest_framework import serializers
from events.serializers import EventSerializer
from contacts.serializers import ContactListSerializer


class ActivityStatsSerializer(serializers.Serializer):
    total_this_month = serializers.IntegerField(read_only=True)
    trend_percent = serializers.FloatField(read_only=True)


class DecayContactSerializer(serializers.Serializer):
    contact = ContactListSerializer(read_only=True)
    days_since_interaction = serializers.IntegerField(read_only=True)


class DashboardSerializer(serializers.Serializer):
    upcoming_events = EventSerializer(many=True, read_only=True)
    recent_events = EventSerializer(many=True, read_only=True)
    activity_stats = ActivityStatsSerializer(read_only=True)
    decay_radar = DecayContactSerializer(many=True, read_only=True)