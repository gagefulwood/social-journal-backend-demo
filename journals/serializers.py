from rest_framework import serializers

from events.models import Event
from lookups.models import EntryTag, Mood
from lookups.serializers import EntryTagSerializer, MoodSerializer

from .models import Exercise, ExerciseStep, Log, Reflection


class VisibleLookupMixin:
    def _request_user(self):
        request = self.context.get('request')
        if request:
            return request.user
        return None

    def _validate_visible_mood(self, mood):
        user = self._request_user()
        if mood and user and not Mood.objects.for_user(user).filter(pk=mood.pk).exists():
            raise serializers.ValidationError({
                'mood_id': 'Select a mood visible to the requesting user.'
            })

    def _validate_visible_tags(self, tags):
        user = self._request_user()
        if not tags or not user:
            return
        visible_ids = set(
            EntryTag.objects.for_user(user)
            .filter(pk__in=[tag.pk for tag in tags])
            .values_list('pk', flat=True)
        )
        missing_ids = [tag.pk for tag in tags if tag.pk not in visible_ids]
        if missing_ids:
            raise serializers.ValidationError({
                'tag_ids': 'Select tags visible to the requesting user.'
            })


class LogListSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    mood = MoodSerializer(read_only=True)
    tags = EntryTagSerializer(many=True, read_only=True)

    class Meta:
        model = Log
        fields = [
            'id',
            'kind',
            'event',
            'title',
            'mood',
            'tags',
            'subtype',
            'created_timestamp',
            'updated_timestamp',
        ]

    def get_kind(self, obj):
        return 'log'


class LogSerializer(VisibleLookupMixin, serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    mood = MoodSerializer(read_only=True)
    mood_id = serializers.PrimaryKeyRelatedField(
        queryset=Mood.objects.all(),
        source='mood',
        write_only=True,
        required=False,
        allow_null=True,
    )
    tags = EntryTagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=EntryTag.objects.all(),
        source='tags',
        many=True,
        write_only=True,
        required=False,
    )

    class Meta:
        model = Log
        fields = [
            'id',
            'kind',
            'event',
            'title',
            'body',
            'mood',
            'mood_id',
            'tags',
            'tag_ids',
            'subtype',
            'data',
            'created_timestamp',
            'updated_timestamp',
        ]
        read_only_fields = ['created_timestamp', 'updated_timestamp']

    def get_kind(self, obj):
        return 'log'

    def validate(self, attrs):
        self._validate_visible_mood(attrs.get('mood'))
        self._validate_visible_tags(attrs.get('tags'))
        return attrs


class ReflectionListSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()

    class Meta:
        model = Reflection
        fields = [
            'id',
            'kind',
            'event',
            'title',
            'subtype',
            'clarity_check',
            'created_timestamp',
            'updated_timestamp',
        ]

    def get_kind(self, obj):
        return 'reflection'


class ReflectionSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()

    class Meta:
        model = Reflection
        fields = [
            'id',
            'kind',
            'event',
            'title',
            'subtype',
            'clarity_check',
            'data',
            'created_timestamp',
            'updated_timestamp',
        ]
        read_only_fields = ['created_timestamp', 'updated_timestamp']

    def get_kind(self, obj):
        return 'reflection'


class ExerciseStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExerciseStep
        fields = ['id', 'display_order', 'prompt', 'response']


class ExerciseListSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    measurement_delta = serializers.IntegerField(read_only=True)

    class Meta:
        model = Exercise
        fields = [
            'id',
            'kind',
            'event',
            'title',
            'subtype',
            'pre_measurement',
            'post_measurement',
            'measurement_delta',
            'created_timestamp',
            'updated_timestamp',
        ]

    def get_kind(self, obj):
        return 'exercise'


class ExerciseSerializer(serializers.ModelSerializer):
    kind = serializers.SerializerMethodField()
    measurement_delta = serializers.IntegerField(read_only=True)
    steps = ExerciseStepSerializer(many=True, required=False)

    class Meta:
        model = Exercise
        fields = [
            'id',
            'kind',
            'event',
            'title',
            'subtype',
            'pre_measurement',
            'post_measurement',
            'measurement_delta',
            'steps',
            'created_timestamp',
            'updated_timestamp',
        ]
        read_only_fields = ['created_timestamp', 'updated_timestamp']

    def get_kind(self, obj):
        return 'exercise'

    def create(self, validated_data):
        steps_data = validated_data.pop('steps', [])
        exercise = Exercise.objects.create(**validated_data)
        self._replace_steps(exercise, steps_data)
        return exercise

    def update(self, instance, validated_data):
        steps_data = validated_data.pop('steps', None)
        instance = super().update(instance, validated_data)
        if steps_data is not None:
            instance.steps.all().delete()
            self._replace_steps(instance, steps_data)
        return instance

    def _replace_steps(self, exercise, steps_data):
        ExerciseStep.objects.bulk_create(
            ExerciseStep(exercise=exercise, **step_data)
            for step_data in steps_data
        )


class CombinedJournalItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    event = serializers.UUIDField()
    label = serializers.CharField()
    created_timestamp = serializers.DateTimeField()
    updated_timestamp = serializers.DateTimeField()
    summary = serializers.JSONField()
