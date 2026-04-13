from rest_framework import serializers
from .models import (
    Occupation,
    EducationLevel,
    ClosenessScore,
    Mood,
    ContextCategory,
    DetailCategory,
    NoteMarker,
    MediaType,
    JournalTag,
)

class OccupationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Occupation
        fields = ["id", "name", "is_system_default"]
        read_only_fields = fields

class EducationLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = EducationLevel
        fields = ["id", "name", "is_system_default"]
        read_only_fields = fields

class ClosenessScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClosenessScore
        fields = ["id", "name"]
        read_only_fields = fields

class MoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mood
        fields = ["id", "name", "emoji_icon", "is_system_default"]
        read_only_fields = fields

class ContextCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContextCategory
        fields = ["id", "name", "color", "is_system_default"]
        read_only_fields = fields

class DetailCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = DetailCategory
        fields = ["id", "name", "icon_reference", "parent"]
        read_only_fields = fields

class NoteMarkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteMarker
        fields = ["id", "name", "color_hex", "icon_reference"]
        read_only_fields = fields

class MediaTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaType
        fields = ["id", "name"]
        read_only_fields = fields

class JournalTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalTag
        fields = ["id", "tag_name", "is_system_default"]
        read_only_fields = fields