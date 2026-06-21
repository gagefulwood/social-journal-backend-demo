from rest_framework import serializers
from django.db.models import Q
from .models import (
    Occupation,
    EducationLevel,
    Relation,
    InteractionMode,
    Mood,
    ContextCategory,
    FactCategory,
    ObservationMarker,
    MediaType,
    EntryTag,
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

class RelationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Relation
        fields = ["id", "name", "is_system_default"]
        read_only_fields = ['is_system_default']

class InteractionModeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionMode
        fields = ["id", "name", "is_system_default"]
        read_only_fields = ['is_system_default']

class MoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mood
        fields = ["id", "name", "emoji_icon", "polarity", "is_system_default"]
        read_only_fields = ['is_system_default']

class ContextCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContextCategory
        fields = ["id", "name", "color", "is_system_default"]
        read_only_fields = ['is_system_default']

class FactCategorySerializer(serializers.ModelSerializer):
    '''
    Serializer for FactCategory that includes nested children.
    Root categories (parent=null) are returned with their full subtree.
    '''
    children = serializers.SerializerMethodField()

    class Meta:
        model = FactCategory
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
        return FactCategorySerializer(
            children, many=True, context=self.context
        ).data

class ObservationMarkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObservationMarker
        fields = ["id", "name", "color_hex", "icon_reference"]
        read_only_fields = ['is_system_default']

class MediaTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaType
        fields = ["id", "name"]
        read_only_fields = fields

class EntryTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryTag
        fields = ["id", "tag_name", "is_system_default"]
        read_only_fields = ['is_system_default']
