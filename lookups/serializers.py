from rest_framework import serializers
from django.db.models import Q
from .models import (
    Occupation,
    EducationLevel,
    ClosenessScore,
    Mood,
    ContextCategory,
    DetailCategoryTree,
    NoteMarker,
    MediaType,
    JournalTag,
)

class OccupationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Occupation
        fields = ["id", "name", "is_system_default"]
        read_only_fields = ['is_system_default']

class EducationLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = EducationLevel
        fields = ["id", "name", "is_system_default"]
        read_only_fields = ['is_system_default']

class ClosenessScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClosenessScore
        fields = ["id", "name"]
        read_only_fields = fields

class MoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mood
        fields = ["id", "name", "emoji_icon", "is_system_default"]
        read_only_fields = ['is_system_default']

class ContextCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContextCategory
        fields = ["id", "name", "color", "is_system_default"]
        read_only_fields = ['is_system_default']

class DetailCategorySerializer(serializers.ModelSerializer):
    '''
    Serializer for DetailCategoryTree that includes nested children.
    Root categories (parent=null) are returned with their full subtree.
    '''
    children = serializers.SerializerMethodField()

    class Meta:
        model = DetailCategoryTree
        fields = ["id", "name", "icon_reference", "parent", "is_system_default", "children"]
        read_only_fields = ['is_system_default']

    def get_children(self, obj):
        '''
        Recursively serializer child categories.
        Only fetches children that are visible to the requesting user
        (system defaults & user-owned).
        '''
        children = obj.children.all()

        # Given user context, filter children to only show defaults and user custom categories
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            children = children.filter(
                Q(is_system_default=True) | Q(user=request.user)
            )
        return DetailCategorySerializer(
            children, many=True, context=self.context
        ).data

class NoteMarkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoteMarker
        fields = ["id", "name", "color_hex", "icon_reference"]
        read_only_fields = ['is_system_default']

class MediaTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaType
        fields = ["id", "name"]
        read_only_fields = fields

class JournalTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalTag
        fields = ["id", "tag_name", "is_system_default"]
        read_only_fields = ['is_system_default']