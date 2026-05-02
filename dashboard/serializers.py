from rest_framework import serializers
from events.serializers import EventSerializer


class ActivityStatsSerializer(serializers.Serializer):
    total_this_month = serializers.IntegerField(read_only=True)
    trend_percent = serializers.FloatField(read_only=True)


class DecayContactSerializer(serializers.Serializer):
    contact_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    last_interaction_date = serializers.DateTimeField(read_only=True)
    days_since = serializers.IntegerField(read_only=True)
    relationship_trend = serializers.CharField(read_only=True)
    connection_strength = serializers.IntegerField(read_only=True)


class DashboardSerializer(serializers.Serializer):
    upcoming_events = EventSerializer(many=True, read_only=True)
    recent_events = EventSerializer(many=True, read_only=True)
    activity_stats = ActivityStatsSerializer(read_only=True)
    decay_radar = DecayContactSerializer(many=True, read_only=True)
