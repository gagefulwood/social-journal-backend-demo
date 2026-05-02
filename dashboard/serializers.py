from rest_framework import serializers
from lookups.serializers import ContextCategorySerializer


class ActivityStatsSerializer(serializers.Serializer):
    entries_total = serializers.IntegerField(read_only=True)
    entries_30d = serializers.IntegerField(read_only=True)
    entries_by_kind_30d = serializers.DictField(
        child=serializers.IntegerField(),
        read_only=True,
    )
    events_30d = serializers.IntegerField(read_only=True)
    current_streak_days = serializers.IntegerField(read_only=True)


class InteractionHeatmapDaySerializer(serializers.Serializer):
    date = serializers.DateField(read_only=True)
    count = serializers.IntegerField(read_only=True)


class DashboardEventSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    event_timestamp = serializers.DateTimeField(read_only=True)
    tier = serializers.CharField(read_only=True)
    context_category = ContextCategorySerializer(read_only=True)
    participant_count = serializers.SerializerMethodField()
    journaled = serializers.BooleanField(read_only=True)

    def get_participant_count(self, obj):
        return obj.participants.count()


class DecayContactSerializer(serializers.Serializer):
    contact_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    last_interaction_date = serializers.DateTimeField(read_only=True)
    days_since = serializers.IntegerField(read_only=True)
    relationship_trend = serializers.CharField(read_only=True)
    connection_strength = serializers.IntegerField(read_only=True)


class DashboardSerializer(serializers.Serializer):
    interaction_heatmap = InteractionHeatmapDaySerializer(many=True, read_only=True)
    upcoming_events = DashboardEventSerializer(many=True, read_only=True)
    recent_events = DashboardEventSerializer(many=True, read_only=True)
    activity_stats = ActivityStatsSerializer(read_only=True)
    decay_radar = DecayContactSerializer(many=True, read_only=True)
