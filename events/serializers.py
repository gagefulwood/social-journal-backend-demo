from django.db import transaction
from rest_framework import serializers

from contacts.models import Contact
from contacts.serializers import ContactListSerializer
from contacts.services import recalculate_contact_statistics
from lookups.models import ContextCategory, InteractionMode, Mood
from lookups.serializers import (
    ContextCategorySerializer,
    InteractionModeSerializer,
    MoodSerializer,
)
from media.serializers import MediaAssetListSerializer
from media.models import MediaAsset
from journals.services import JournalSummaryQuery

from .models import (
    Event,
    EventChapter,
    EventChapterParticipant,
    EventMedia,
    EventMediaCrop,
    EventParticipant,
)
from .services import (
    UNSET,
    validate_event_end_against_chapters,
    validate_event_participant_replacement,
)

EVENT_JOURNAL_PREVIEW_LIMIT = 4


class EventParticipantContactSerializer(ContactListSerializer):
    profile_picture = serializers.SerializerMethodField()

    def get_profile_picture(self, obj):
        profile_picture = obj.profile_picture
        if (
            profile_picture is None
            or not profile_picture.is_active
            or profile_picture.user_id != obj.user_id
        ):
            return None
        return MediaAssetListSerializer(
            profile_picture,
            context=self.context,
        ).data


class EventParticipantSerializer(serializers.ModelSerializer):
    contact = EventParticipantContactSerializer(read_only=True)

    class Meta:
        model = EventParticipant
        fields = ['id', 'contact']


def _media_asset_is_ready(asset):
    return asset.is_active and getattr(asset, 'status', 'ready') == 'ready'


def _media_content_type(asset):
    return (
        getattr(asset, 'detected_content_type', '')
        or getattr(asset, 'detected_mime_type', '')
        or asset.content_type
    ).lower()


class EventMediaCropSerializer(serializers.ModelSerializer):
    x = serializers.DecimalField(
        max_digits=6,
        decimal_places=5,
        coerce_to_string=False,
    )
    y = serializers.DecimalField(
        max_digits=6,
        decimal_places=5,
        coerce_to_string=False,
    )
    width = serializers.DecimalField(
        max_digits=6,
        decimal_places=5,
        coerce_to_string=False,
    )
    height = serializers.DecimalField(
        max_digits=6,
        decimal_places=5,
        coerce_to_string=False,
    )

    class Meta:
        model = EventMediaCrop
        fields = [
            'id',
            'crop_kind',
            'x',
            'y',
            'width',
            'height',
            'source_orientation_revision',
        ]
        read_only_fields = ['id']


class EventMediaAttachmentSerializer(serializers.ModelSerializer):
    event_id = serializers.IntegerField(read_only=True)
    chapter_id = serializers.UUIDField(read_only=True, allow_null=True)
    media_asset = MediaAssetListSerializer(read_only=True)
    focal_x = serializers.SerializerMethodField()
    focal_y = serializers.SerializerMethodField()
    crops = EventMediaCropSerializer(many=True, read_only=True)

    class Meta:
        model = EventMedia
        fields = [
            'id',
            'event_id',
            'chapter_id',
            'media_asset',
            'display_order',
            'recorded_at',
            'alt_text',
            'caption',
            'decorative',
            'is_cover',
            'focal_x',
            'focal_y',
            'crops',
            'created_timestamp',
            'updated_timestamp',
        ]
        read_only_fields = fields

    def get_focal_x(self, obj):
        if not _media_content_type(obj.media_asset).startswith('image/'):
            return None
        return float(obj.focal_x)

    def get_focal_y(self, obj):
        if not _media_content_type(obj.media_asset).startswith('image/'):
            return None
        return float(obj.focal_y)


class EventChapterHeaderSerializer(serializers.ModelSerializer):
    effective_location_label = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    participant_preview = serializers.SerializerMethodField()
    media_count = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = EventChapter
        fields = [
            'id',
            'title',
            'position',
            'start_timestamp',
            'end_timestamp',
            'location_label',
            'effective_location_label',
            'inherits_event_participants',
            'participant_count',
            'participant_preview',
            'media_count',
            'thumbnail',
        ]

    def get_effective_location_label(self, obj):
        event = self._event(obj)
        return obj.location_label or event.location_label

    def get_participant_count(self, obj):
        return len(self._effective_contacts(obj))

    def get_participant_preview(self, obj):
        return [
            EventParticipantContactSerializer(
                contact,
                context=self.context,
            ).data
            for contact in self._effective_contacts(obj)[:3]
        ]

    def get_media_count(self, obj):
        return len(self._media(obj))

    def get_thumbnail(self, obj):
        media = self._media(obj)
        image = next(
            (
                attachment
                for attachment in media
                if attachment.is_cover
                and _media_content_type(attachment.media_asset).startswith('image/')
            ),
            None,
        )
        if image is None:
            image = next(
                (
                    attachment
                    for attachment in media
                    if _media_content_type(attachment.media_asset).startswith('image/')
                ),
                None,
            )
        if image is None:
            return None
        return EventMediaAttachmentSerializer(
            image,
            context=self.context,
        ).data

    def _event(self, obj):
        return self.context.get('event') or obj.event

    def _effective_contacts(self, obj):
        if obj.inherits_event_participants:
            participants = self._event(obj).participants.all()
            return [participant.contact for participant in participants]
        links = obj.participant_links.all()
        return [link.contact for link in links]

    def _media(self, obj):
        attachments = getattr(obj, 'ready_media', None)
        if attachments is None:
            attachments = obj.media_attachments.select_related(
                'media_asset',
                'media_asset__media_type',
            ).prefetch_related('crops')
        return [
            attachment
            for attachment in attachments
            if _media_asset_is_ready(attachment.media_asset)
        ]


class EventChapterDetailSerializer(EventChapterHeaderSerializer):
    is_projection = serializers.SerializerMethodField()
    effective_start_timestamp = serializers.SerializerMethodField()
    effective_end_timestamp = serializers.SerializerMethodField()
    effective_participants = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    journals = serializers.SerializerMethodField()

    class Meta(EventChapterHeaderSerializer.Meta):
        fields = [
            'id',
            'is_projection',
            'title',
            'position',
            'start_timestamp',
            'end_timestamp',
            'effective_start_timestamp',
            'effective_end_timestamp',
            'location_label',
            'effective_location_label',
            'note',
            'inherits_event_participants',
            'participant_count',
            'participant_preview',
            'effective_participants',
            'media_count',
            'thumbnail',
            'media',
            'journals',
            'created_timestamp',
            'updated_timestamp',
        ]

    def get_is_projection(self, obj):
        return False

    def get_effective_start_timestamp(self, obj):
        return obj.start_timestamp or self._event(obj).event_timestamp

    def get_effective_end_timestamp(self, obj):
        return obj.end_timestamp or self._event(obj).end_timestamp

    def get_effective_participants(self, obj):
        return [
            EventParticipantContactSerializer(
                contact,
                context=self.context,
            ).data
            for contact in self._effective_contacts(obj)
        ]

    def get_media(self, obj):
        return EventMediaAttachmentSerializer(
            self._media(obj),
            many=True,
            context=self.context,
        ).data

    def get_journals(self, obj):
        return JournalSummaryQuery(
            user=self._event(obj).user,
            event=self._event(obj),
            chapter=obj,
        ).fetch()


class EventChapterWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    start_timestamp = serializers.DateTimeField(required=False, allow_null=True)
    end_timestamp = serializers.DateTimeField(required=False, allow_null=True)
    location_label = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    note = serializers.CharField(required=False, allow_blank=True)
    inherits_event_participants = serializers.BooleanField(required=False)
    participant_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Contact.objects.all(),
        source='participant_contacts',
        required=False,
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            fields['participant_ids'].child_relation.queryset = (
                Contact.objects.for_user(request.user)
            )
        return fields

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter a chapter title.')
        return value


class EventChapterReorderSerializer(serializers.Serializer):
    chapter_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
    )


class EventMediaWriteSerializer(serializers.Serializer):
    media_asset_id = serializers.PrimaryKeyRelatedField(
        queryset=MediaAsset.objects.all(),
        source='media_asset',
        required=True,
    )
    chapter_id = serializers.PrimaryKeyRelatedField(
        queryset=EventChapter.objects.all(),
        source='chapter',
        required=False,
        allow_null=True,
    )
    recorded_at = serializers.DateTimeField(required=False, allow_null=True)
    alt_text = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
    )
    caption = serializers.CharField(required=False, allow_blank=True)
    decorative = serializers.BooleanField(required=False)
    is_cover = serializers.BooleanField(required=False)
    focal_x = serializers.DecimalField(
        max_digits=6,
        decimal_places=5,
        min_value=0,
        max_value=1,
        required=False,
    )
    focal_y = serializers.DecimalField(
        max_digits=6,
        decimal_places=5,
        min_value=0,
        max_value=1,
        required=False,
    )
    crops = EventMediaCropSerializer(many=True, required=False)

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        event = self.context.get('event')
        if request and request.user.is_authenticated:
            fields['media_asset_id'].queryset = MediaAsset.objects.for_user(
                request.user,
            )
            fields['chapter_id'].queryset = EventChapter.objects.filter(
                event=event,
                event__user=request.user,
            )
        return fields

    def validate(self, attrs):
        asset = attrs.get('media_asset')
        if asset and 'alt_text' not in attrs and asset.alt_text:
            attrs['alt_text'] = asset.alt_text
        return attrs


class EventMediaReorderSerializer(serializers.Serializer):
    chapter_id = serializers.PrimaryKeyRelatedField(
        queryset=EventChapter.objects.all(),
        source='chapter',
        required=False,
        allow_null=True,
    )
    media_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
    )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        event = self.context.get('event')
        if request and request.user.is_authenticated:
            fields['chapter_id'].queryset = EventChapter.objects.filter(
                event=event,
                event__user=request.user,
            )
        return fields


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
    context_category_summary = ContextCategorySerializer(
        source='context_category',
        read_only=True,
    )
    chapter_mode = serializers.SerializerMethodField()
    chapters = serializers.SerializerMethodField()
    legacy_chapter = serializers.SerializerMethodField()
    media_summary = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'user', 'title', 'description', 'event_timestamp',
            'end_timestamp', 'location_label', 'tier', 'impact',
            'context_category', 'context_category_summary',
            'interaction_mode', 'interaction_mode_id',
            'mood', 'mood_id', 'participants', 'journaled', 'journals',
            'chapter_mode', 'chapters', 'legacy_chapter', 'media_summary',
        ]
        read_only_fields = [
            'user',
            'journaled',
            'journals',
            'context_category_summary',
            'chapter_mode',
            'chapters',
            'legacy_chapter',
            'media_summary',
        ]

    def get_fields(self):
        fields = super().get_fields()
        user = self._request_user()
        if user:
            fields['participants'].child_relation.queryset = (
                Contact.objects.for_user(user)
            )
            fields['context_category'].queryset = (
                ContextCategory.objects.for_user(user)
            )
            fields['interaction_mode_id'].queryset = (
                InteractionMode.objects.for_user(user)
            )
            fields['mood_id'].queryset = Mood.objects.for_user(user)
        return fields

    def validate(self, attrs):
        if self.instance and 'event_timestamp' in attrs:
            if attrs['event_timestamp'] != self.instance.event_timestamp:
                raise serializers.ValidationError({
                    'event_timestamp': 'Event timestamp cannot be changed after creation.'
                })

        if 'end_timestamp' in attrs and attrs['end_timestamp'] is not None:
            event_timestamp = (
                self.instance.event_timestamp
                if self.instance
                else attrs.get('event_timestamp')
            )
            if event_timestamp and attrs['end_timestamp'] < event_timestamp:
                raise serializers.ValidationError({
                    'end_timestamp': (
                        'End timestamp must be on or after the event timestamp.'
                    )
                })

        user = self._request_user()
        if user:
            self._validate_visible_lookup(
                'context_category',
                attrs.get('context_category'),
                ContextCategory,
                user,
            )
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

    @transaction.atomic
    def create(self, validated_data):
        participant_contacts = validated_data.pop('participant_contacts', [])
        self._validate_participant_contacts(participant_contacts, validated_data['user'])
        self._validate_visible_lookup(
            'context_category',
            validated_data.get('context_category'),
            ContextCategory,
            validated_data['user'],
        )
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

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = Event.objects.select_for_update().get(
            pk=instance.pk,
            user=instance.user,
        )
        participant_contacts = validated_data.pop('participant_contacts', None)
        if participant_contacts is not None:
            self._validate_participant_contacts(participant_contacts, instance.user)
            validate_event_participant_replacement(
                event=instance,
                requested_contacts=self._unique_contacts(participant_contacts),
            )
        if 'end_timestamp' in validated_data:
            validate_event_end_against_chapters(
                instance,
                validated_data['end_timestamp'],
            )
        context_category_changed = (
            'context_category' in validated_data
            and getattr(validated_data['context_category'], 'id', None)
            != instance.context_category_id
        )
        self._validate_visible_lookup(
            'context_category',
            validated_data.get('context_category'),
            ContextCategory,
            instance.user,
        )
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
        if context_category_changed:
            participants = EventParticipant.objects.filter(
                event=instance,
            ).select_related('contact')
            for participant in participants:
                recalculate_contact_statistics(participant.contact)
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
        cached = getattr(obj, '_whole_event_journal_summary', None)
        if cached is None:
            cached = JournalSummaryQuery(
                user=obj.user,
                event=obj,
                chapter=None,
            ).fetch()
            obj._whole_event_journal_summary = cached
        return cached

    def get_chapter_mode(self, obj):
        return 'persisted' if self._chapters(obj) else 'projected'

    def get_chapters(self, obj):
        chapters = self._chapters(obj)
        if not chapters:
            return []
        return EventChapterHeaderSerializer(
            chapters,
            many=True,
            context={**self.context, 'event': obj},
        ).data

    def get_legacy_chapter(self, obj):
        if self._chapters(obj):
            return None
        contacts = [
            participant.contact
            for participant in obj.participants.all()
        ]
        media = self._whole_event_media(obj)
        participant_preview = [
            EventParticipantContactSerializer(
                contact,
                context=self.context,
            ).data
            for contact in contacts[:3]
        ]
        thumbnail = next(
            (
                attachment
                for attachment in media
                if attachment.is_cover
                and _media_content_type(attachment.media_asset).startswith(
                    'image/'
                )
            ),
            None,
        )
        if thumbnail is None:
            thumbnail = next(
                (
                    attachment
                    for attachment in media
                    if _media_content_type(attachment.media_asset).startswith(
                        'image/'
                    )
                ),
                None,
            )
        return {
            'id': None,
            'is_projection': True,
            'title': obj.title,
            'position': 0,
            'start_timestamp': obj.event_timestamp,
            'end_timestamp': obj.end_timestamp,
            'effective_start_timestamp': obj.event_timestamp,
            'effective_end_timestamp': obj.end_timestamp,
            'location_label': obj.location_label,
            'effective_location_label': obj.location_label,
            'note': obj.description,
            'inherits_event_participants': True,
            'participant_count': len(contacts),
            'participant_preview': participant_preview,
            'effective_participants': [
                EventParticipantContactSerializer(
                    contact,
                    context=self.context,
                ).data
                for contact in contacts
            ],
            'media_count': len(media),
            'thumbnail': (
                EventMediaAttachmentSerializer(
                    thumbnail,
                    context=self.context,
                ).data
                if thumbnail is not None
                else None
            ),
            'media': EventMediaAttachmentSerializer(
                media,
                many=True,
                context=self.context,
            ).data,
            'journals': self.get_journals(obj),
        }

    def get_media_summary(self, obj):
        all_media = self._all_event_media(obj)
        whole_media = [
            attachment
            for attachment in all_media
            if attachment.chapter_id is None
        ]
        cover = next(
            (attachment for attachment in whole_media if attachment.is_cover),
            None,
        )
        ordered_previews = []
        if cover is not None:
            ordered_previews.append(cover)
        ordered_previews.extend(
            attachment
            for attachment in whole_media
            if (cover is None or attachment.id != cover.id)
            and _media_content_type(attachment.media_asset).startswith(
                ('image/', 'video/')
            )
        )
        content_types = [
            _media_content_type(attachment.media_asset)
            for attachment in all_media
        ]
        return {
            'total_count': len(all_media),
            'image_count': sum(
                content_type.startswith('image/')
                for content_type in content_types
            ),
            'video_count': sum(
                content_type.startswith('video/')
                for content_type in content_types
            ),
            'audio_count': sum(
                content_type.startswith('audio/')
                for content_type in content_types
            ),
            'cover': (
                EventMediaAttachmentSerializer(
                    cover,
                    context=self.context,
                ).data
                if cover is not None
                else None
            ),
            'previews': EventMediaAttachmentSerializer(
                ordered_previews[:3],
                many=True,
                context=self.context,
            ).data,
        }

    def _chapters(self, obj):
        chapters = getattr(obj, 'chapter_headers', None)
        if chapters is None:
            chapters = list(
                obj.chapters.select_related('event')
                .prefetch_related(
                    'participant_links__contact',
                    'media_attachments__media_asset__media_type',
                    'media_attachments__crops',
                )
                .order_by('position', 'id')
            )
        all_media = getattr(obj, 'ready_event_media', None)
        if all_media is not None:
            media_by_chapter = {}
            for attachment in all_media:
                if attachment.chapter_id is not None:
                    media_by_chapter.setdefault(attachment.chapter_id, []).append(
                        attachment
                    )
            for chapter in chapters:
                chapter.ready_media = media_by_chapter.get(chapter.id, [])
        return chapters

    def _all_event_media(self, obj):
        attachments = getattr(obj, 'ready_event_media', None)
        if attachments is None:
            attachments = list(
                obj.media_attachments.select_related(
                    'media_asset',
                    'media_asset__media_type',
                ).prefetch_related('crops')
            )
        return [
            attachment
            for attachment in attachments
            if _media_asset_is_ready(attachment.media_asset)
        ]

    def _whole_event_media(self, obj):
        return [
            attachment
            for attachment in self._all_event_media(obj)
            if attachment.chapter_id is None
        ]

    def _validate_participant_contacts(self, contacts, user):
        invalid_contacts = [
            contact
            for contact in contacts
            if contact.user_id != user.id or not contact.is_active
        ]
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
            for participant in EventParticipant.objects.filter(
                event=event,
            ).select_related('contact')
        }
        existing_ids = set(existing_participants)

        for contact in requested_contacts:
            if contact.id not in existing_ids:
                EventParticipant.objects.create(event=event, contact=contact)

        for contact_id in existing_ids - requested_ids:
            existing_participants[contact_id].delete()

        prefetched_objects = getattr(event, '_prefetched_objects_cache', None)
        if prefetched_objects is not None:
            prefetched_objects.pop('participants', None)

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
