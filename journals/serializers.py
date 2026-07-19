from django.db import transaction
from rest_framework import serializers

from contacts.models import Contact
from events.models import Event
from lookups.models import (
    EmotionState,
    EpisodeCategory,
    EpisodeCharacteristic,
    EpisodeContextTag,
    FactCategory,
    InteractionDynamic,
    ObservationMarker,
    SocialEnergyFactor,
)
from media.models import MediaAsset

from .models import (
    CarryForwardFactDraft,
    CarryForwardObservationDraft,
    EmotionalManifestation,
    EmotionalReflectionDetail,
    EpisodeLogDetail,
    FreeReflectionDetail,
    InteractionReflectionDetail,
    Log,
    MomentReflectionDetail,
    Reflection,
    ReflectionAttachment,
    ReflectionContact,
    SentimentLogDetail,
    SocialEnergyLogDetail,
)
from .services import progress_for


UNSET = object()


def _request_user(serializer):
    request = serializer.context.get('request')
    if request and request.user and request.user.is_authenticated:
        return request.user
    return None


def _has_meaningful_value(value):
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_meaningful_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_meaningful_value(item) for item in value)
    return True


def _event_summary(event):
    if event is None:
        return None
    return {
        'id': event.id,
        'title': event.title,
        'start_timestamp': event.event_timestamp,
        'end_timestamp': event.end_timestamp,
        'location': event.location_label or None,
    }


def _contact_summary(contact):
    if contact is None:
        return None
    return {
        'id': contact.id,
        'display_name': str(contact),
    }


class VisibleDetailSerializer(serializers.ModelSerializer):
    visible_fields = {}

    def validate(self, attrs):
        user = _request_user(self)
        if not user:
            return attrs
        errors = {}
        for field_name, model in self.visible_fields.items():
            value = attrs.get(field_name)
            values = value if isinstance(value, list) else [value]
            ids = [item.pk for item in values if item is not None]
            if not ids:
                continue
            visible_ids = set(
                model.objects.for_user(user)
                .filter(pk__in=ids)
                .values_list('pk', flat=True)
            )
            if any(item_id not in visible_ids for item_id in ids):
                errors[field_name] = (
                    'Select lookup rows visible to the requesting user.'
                )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class EpisodeDetailSerializer(VisibleDetailSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=EpisodeCategory.objects.all(),
        source='category',
        required=False,
        allow_null=True,
    )
    characteristic_ids = serializers.PrimaryKeyRelatedField(
        queryset=EpisodeCharacteristic.objects.all(),
        source='characteristics',
        many=True,
        required=False,
    )
    context_tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=EpisodeContextTag.objects.all(),
        source='context_tags',
        many=True,
        required=False,
    )
    visible_fields = {
        'category': EpisodeCategory,
        'characteristics': EpisodeCharacteristic,
        'context_tags': EpisodeContextTag,
    }

    class Meta:
        model = EpisodeLogDetail
        fields = [
            'category_id',
            'ended_at',
            'is_ongoing',
            'characteristic_ids',
            'context_tag_ids',
        ]


class SocialEnergyDetailSerializer(VisibleDetailSerializer):
    factor_ids = serializers.PrimaryKeyRelatedField(
        queryset=SocialEnergyFactor.objects.all(),
        source='factors',
        many=True,
        required=False,
    )
    visible_fields = {'factors': SocialEnergyFactor}

    class Meta:
        model = SocialEnergyLogDetail
        fields = [
            'before_state',
            'battery_effect',
            'mood_shift',
            'behavioral_effect',
            'recovery_timing',
            'interaction_context',
            'group_size',
            'familiarity',
            'setting',
            'factor_ids',
        ]
        extra_kwargs = {
            field: {'required': False, 'allow_blank': True}
            for field in (
                'before_state',
                'battery_effect',
                'mood_shift',
                'behavioral_effect',
                'recovery_timing',
                'interaction_context',
                'familiarity',
                'setting',
            )
        }


class SentimentDetailSerializer(VisibleDetailSerializer):
    before_state_id = serializers.PrimaryKeyRelatedField(
        queryset=EmotionState.objects.all(),
        source='before_state',
        required=False,
        allow_null=True,
    )
    after_state_id = serializers.PrimaryKeyRelatedField(
        queryset=EmotionState.objects.all(),
        source='after_state',
        required=False,
        allow_null=True,
    )
    dynamic_ids = serializers.PrimaryKeyRelatedField(
        queryset=InteractionDynamic.objects.all(),
        source='dynamics',
        many=True,
        required=False,
    )
    visible_fields = {
        'before_state': EmotionState,
        'after_state': EmotionState,
        'dynamics': InteractionDynamic,
    }

    class Meta:
        model = SentimentLogDetail
        fields = [
            'before_state_id',
            'after_state_id',
            'before_connection',
            'after_connection',
            'dynamic_ids',
            'initiated_by',
            'overall_exchange',
        ]
        extra_kwargs = {
            field: {'required': False, 'allow_blank': True}
            for field in (
                'before_connection',
                'after_connection',
                'initiated_by',
                'overall_exchange',
            )
        }


class InteractionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionReflectionDetail
        exclude = ['reflection']
        extra_kwargs = {
            field.name: {'required': False, 'allow_blank': True}
            for field in InteractionReflectionDetail._meta.fields
            if field.name != 'reflection'
        }


class MomentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = MomentReflectionDetail
        exclude = ['reflection']
        extra_kwargs = {
            field.name: {'required': False, 'allow_blank': True}
            for field in MomentReflectionDetail._meta.fields
            if field.name != 'reflection'
        }


class ManifestationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)

    class Meta:
        model = EmotionalManifestation
        fields = ['id', 'kind', 'text', 'display_order']


class EmotionalDetailSerializer(VisibleDetailSerializer):
    emotion_ids = serializers.PrimaryKeyRelatedField(
        queryset=EmotionState.objects.all(),
        source='emotions',
        many=True,
        required=False,
    )
    manifestations = ManifestationSerializer(many=True, required=False)
    visible_fields = {'emotions': EmotionState}

    class Meta:
        model = EmotionalReflectionDetail
        fields = [
            'emotion_ids',
            'situation',
            'manifestations',
            'connected_factors',
            'communicating',
            'understanding_now',
            'additional_writing',
        ]
        extra_kwargs = {
            field: {'required': False, 'allow_blank': True}
            for field in (
                'situation',
                'connected_factors',
                'communicating',
                'understanding_now',
                'additional_writing',
            )
        }


class FreeDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreeReflectionDetail
        fields = ['body']
        extra_kwargs = {'body': {'required': False, 'allow_blank': True}}


LOG_DETAIL_SERIALIZERS = {
    Log.FORMAT_EPISODE: EpisodeDetailSerializer,
    Log.FORMAT_SOCIAL_ENERGY: SocialEnergyDetailSerializer,
    Log.FORMAT_SENTIMENT: SentimentDetailSerializer,
}
LOG_DETAIL_RELATIONS = {
    Log.FORMAT_EPISODE: 'episode_detail',
    Log.FORMAT_SOCIAL_ENERGY: 'social_energy_detail',
    Log.FORMAT_SENTIMENT: 'sentiment_detail',
}
LOG_DETAIL_MODELS = {
    Log.FORMAT_EPISODE: EpisodeLogDetail,
    Log.FORMAT_SOCIAL_ENERGY: SocialEnergyLogDetail,
    Log.FORMAT_SENTIMENT: SentimentLogDetail,
}
REFLECTION_DETAIL_SERIALIZERS = {
    Reflection.FORMAT_INTERACTION: InteractionDetailSerializer,
    Reflection.FORMAT_MOMENT: MomentDetailSerializer,
    Reflection.FORMAT_EMOTIONAL: EmotionalDetailSerializer,
    Reflection.FORMAT_FREE: FreeDetailSerializer,
}
REFLECTION_DETAIL_RELATIONS = {
    Reflection.FORMAT_INTERACTION: 'interaction_detail',
    Reflection.FORMAT_MOMENT: 'moment_detail',
    Reflection.FORMAT_EMOTIONAL: 'emotional_detail',
    Reflection.FORMAT_FREE: 'free_detail',
}
REFLECTION_DETAIL_MODELS = {
    Reflection.FORMAT_INTERACTION: InteractionReflectionDetail,
    Reflection.FORMAT_MOMENT: MomentReflectionDetail,
    Reflection.FORMAT_EMOTIONAL: EmotionalReflectionDetail,
    Reflection.FORMAT_FREE: FreeReflectionDetail,
}


class CanonicalJournalSerializer(serializers.ModelSerializer):
    family = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()
    event_id = serializers.PrimaryKeyRelatedField(
        queryset=Event.objects.all(),
        source='event',
        write_only=True,
        required=False,
        allow_null=True,
    )
    primary_contact = serializers.SerializerMethodField()
    primary_contact_id = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.all(),
        source='primary_contact',
        write_only=True,
        required=False,
        allow_null=True,
    )
    detail = serializers.JSONField(write_only=True, required=False)
    expected_revision = serializers.IntegerField(
        min_value=1,
        write_only=True,
        required=False,
    )
    progress = serializers.SerializerMethodField()

    def get_family(self, obj):
        return self.family_name

    def get_event(self, obj):
        return _event_summary(obj.event)

    def get_primary_contact(self, obj):
        return _contact_summary(obj.primary_contact)

    def get_progress(self, obj):
        return progress_for(obj)

    def validate(self, attrs):
        user = _request_user(self)
        event = attrs.get('event')
        primary_contact = attrs.get('primary_contact')
        if event and user and event.user_id != user.id:
            raise serializers.ValidationError({
                'event_id': 'Select an event owned by the requesting user.'
            })
        if primary_contact and user and primary_contact.user_id != user.id:
            raise serializers.ValidationError({
                'primary_contact_id': (
                    'Select a contact owned by the requesting user.'
                )
            })
        if self.instance:
            requested_format = attrs.get('format', self.instance.format)
            if self.instance.format == 'legacy':
                raise serializers.ValidationError({
                    'format': 'Legacy journals are read-only.'
                })
            if requested_format != self.instance.format:
                raise serializers.ValidationError({
                    'format': 'Journal format cannot be changed after creation.'
                })
            if 'expected_revision' not in attrs:
                raise serializers.ValidationError({
                    'expected_revision': 'This field is required for updates.'
                })
        else:
            requested_format = attrs.get('format')
            if requested_format == 'legacy':
                raise serializers.ValidationError({
                    'format': 'Legacy is reserved for migrated records.'
                })
        if 'detail' in attrs:
            attrs['detail'] = self._validated_detail(
                requested_format,
                attrs['detail'],
            )
        if not self.instance and not self._is_meaningful(attrs):
            raise serializers.ValidationError({
                'detail': (
                    'Add meaningful journal content before starting a draft.'
                )
            })
        return attrs

    def _validated_detail(self, journal_format, detail):
        serializer_class = self.detail_serializers.get(journal_format)
        if not serializer_class:
            raise serializers.ValidationError({
                'format': 'Select a supported journal format.'
            })
        serializer = serializer_class(
            data=detail,
            context=self.context,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _is_meaningful(self, attrs):
        ignored = {'format', 'current_step', 'expected_revision'}
        return any(
            _has_meaningful_value(value)
            for key, value in attrs.items()
            if key not in ignored
        )

    def _detail_representation(self, obj):
        if obj.format == 'legacy':
            return {
                'subtype': obj.subtype,
                'data': obj.data,
                **(
                    {
                        'body': obj.body,
                        'mood_id': obj.mood_id,
                        'tag_ids': list(obj.tags.values_list('id', flat=True)),
                    }
                    if isinstance(obj, Log)
                    else {'clarity_check': obj.clarity_check}
                ),
            }
        relation = self.detail_relations.get(obj.format)
        serializer_class = self.detail_serializers.get(obj.format)
        detail = getattr(obj, relation, None) if relation else None
        return (
            serializer_class(detail, context=self.context).data
            if detail and serializer_class
            else {}
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['detail'] = self._detail_representation(instance)
        return data


class LogSerializer(CanonicalJournalSerializer):
    family_name = 'log'
    detail_serializers = LOG_DETAIL_SERIALIZERS
    detail_relations = LOG_DETAIL_RELATIONS

    class Meta:
        model = Log
        fields = [
            'id',
            'family',
            'format',
            'status',
            'title',
            'event',
            'event_id',
            'primary_contact',
            'primary_contact_id',
            'occurred_at',
            'current_step',
            'progress',
            'revision',
            'expected_revision',
            'detail',
            'created_timestamp',
            'updated_timestamp',
            'completed_at',
        ]
        read_only_fields = [
            'status',
            'revision',
            'created_timestamp',
            'updated_timestamp',
            'completed_at',
        ]

    @transaction.atomic
    def create(self, validated_data):
        detail = validated_data.pop('detail', {})
        validated_data.pop('expected_revision', None)
        log = Log.objects.create(
            user=_request_user(self),
            status=Log.STATUS_DRAFT,
            **validated_data,
        )
        self._save_detail(log, detail)
        return log

    @transaction.atomic
    def update(self, instance, validated_data):
        detail = validated_data.pop('detail', None)
        validated_data.pop('expected_revision', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.revision += 1
        instance.save()
        if detail is not None:
            self._save_detail(instance, detail)
        return instance

    def _save_detail(self, log, values):
        model = LOG_DETAIL_MODELS[log.format]
        detail, _ = model.objects.get_or_create(log=log)
        many_fields = {
            'characteristics',
            'context_tags',
            'factors',
            'dynamics',
        }
        many_values = {
            key: values.pop(key)
            for key in list(values)
            if key in many_fields
        }
        for field, value in values.items():
            setattr(detail, field, value)
        detail.save()
        for field, value in many_values.items():
            getattr(detail, field).set(value)


class ReflectionSerializer(CanonicalJournalSerializer):
    family_name = 'reflection'
    detail_serializers = REFLECTION_DETAIL_SERIALIZERS
    detail_relations = REFLECTION_DETAIL_RELATIONS

    contact_ids = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    attachments = serializers.JSONField(write_only=True, required=False)
    cover_media_asset_id = serializers.PrimaryKeyRelatedField(
        queryset=MediaAsset.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    carry_forward = serializers.JSONField(write_only=True, required=False)
    contacts = serializers.SerializerMethodField()
    cover_attachment_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Reflection
        fields = [
            'id',
            'family',
            'format',
            'status',
            'title',
            'event',
            'event_id',
            'primary_contact',
            'primary_contact_id',
            'contact_ids',
            'contacts',
            'occurred_at',
            'current_step',
            'progress',
            'revision',
            'expected_revision',
            'detail',
            'attachments',
            'cover_media_asset_id',
            'cover_attachment_id',
            'carry_forward',
            'created_timestamp',
            'updated_timestamp',
            'completed_at',
        ]
        read_only_fields = [
            'status',
            'revision',
            'created_timestamp',
            'updated_timestamp',
            'completed_at',
        ]

    def get_contacts(self, obj):
        return [_contact_summary(contact) for contact in obj.contacts.all()]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = _request_user(self)
        contacts = attrs.get('contact_ids')
        if contacts is not None and any(
            contact.user_id != user.id for contact in contacts
        ):
            raise serializers.ValidationError({
                'contact_ids': 'Select contacts owned by the requesting user.'
            })
        primary = attrs.get(
            'primary_contact',
            self.instance.primary_contact if self.instance else None,
        )
        if contacts is not None and primary and primary not in contacts:
            contacts.append(primary)
        if 'attachments' in attrs:
            attrs['attachments'] = self._validate_attachments(attrs['attachments'])
        cover = attrs.get('cover_media_asset_id')
        if cover and cover.user_id != user.id:
            raise serializers.ValidationError({
                'cover_media_asset_id': (
                    'Select a media asset owned by the requesting user.'
                )
            })
        if 'carry_forward' in attrs:
            attrs['carry_forward'] = self._validate_carry_forward(
                attrs['carry_forward']
            )
        return attrs

    def _is_meaningful(self, attrs):
        return super()._is_meaningful(attrs) or any(
            _has_meaningful_value(attrs.get(key))
            for key in ('contact_ids', 'attachments', 'carry_forward')
        )

    def _validate_attachments(self, items):
        if not isinstance(items, list):
            raise serializers.ValidationError({
                'attachments': 'Expected a list of attachments.'
            })
        user = _request_user(self)
        validated = []
        seen = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict) or not item.get('media_asset_id'):
                raise serializers.ValidationError({
                    'attachments': (
                        f'Attachment {index} requires media_asset_id.'
                    )
                })
            try:
                media = MediaAsset.objects.for_user(user).get(
                    pk=item['media_asset_id']
                )
            except (MediaAsset.DoesNotExist, ValueError, TypeError):
                raise serializers.ValidationError({
                    'attachments': (
                        f'Attachment {index} is not visible to this user.'
                    )
                })
            if media.pk in seen:
                raise serializers.ValidationError({
                    'attachments': 'A media asset can be attached only once.'
                })
            seen.add(media.pk)
            recorded_at = item.get('recorded_at')
            if recorded_at is not None:
                recorded_at = serializers.DateTimeField().run_validation(
                    recorded_at
                )
            validated.append({
                'media_asset': media,
                'is_sensitive': bool(item.get('is_sensitive', False)),
                'recorded_at': recorded_at,
                'display_order': item.get('display_order', index),
            })
        return validated

    def _validate_carry_forward(self, payload):
        if not isinstance(payload, dict):
            raise serializers.ValidationError({
                'carry_forward': 'Expected an object.'
            })
        return {
            'facts': self._validate_fact_drafts(payload.get('facts', [])),
            'observations': self._validate_observation_drafts(
                payload.get('observations', [])
            ),
        }

    def _owned_contact(self, contact_id, field):
        user = _request_user(self)
        try:
            return Contact.objects.for_user(user).get(pk=contact_id)
        except (Contact.DoesNotExist, ValueError, TypeError):
            raise serializers.ValidationError({
                field: 'Select a contact owned by the requesting user.'
            })

    def _visible_lookup(self, model, lookup_id, field):
        if lookup_id in (None, ''):
            return None
        user = _request_user(self)
        try:
            return model.objects.for_user(user).get(pk=lookup_id)
        except (model.DoesNotExist, ValueError, TypeError):
            raise serializers.ValidationError({
                field: 'Select a lookup visible to the requesting user.'
            })

    def _validate_fact_drafts(self, items):
        validated = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise serializers.ValidationError({
                    'carry_forward': f'Fact {index} must be an object.'
                })
            detail_value = str(item.get('detail_value', '')).strip()
            if not detail_value:
                raise serializers.ValidationError({
                    'carry_forward': f'Fact {index} requires detail_value.'
                })
            validated.append({
                'id': item.get('id'),
                'target_contact': self._owned_contact(
                    item.get('target_contact_id'),
                    'carry_forward.facts.target_contact_id',
                ),
                'category': self._visible_lookup(
                    FactCategory,
                    item.get('category_id'),
                    'carry_forward.facts.category_id',
                ),
                'label': str(item.get('label', '')).strip(),
                'detail_value': detail_value,
                'is_conversation_cue': bool(
                    item.get('is_conversation_cue', False)
                ),
            })
        return validated

    def _validate_observation_drafts(self, items):
        validated = []
        user = _request_user(self)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise serializers.ValidationError({
                    'carry_forward': f'Observation {index} must be an object.'
                })
            body = str(item.get('body', '')).strip()
            if not body:
                raise serializers.ValidationError({
                    'carry_forward': f'Observation {index} requires body.'
                })
            event = None
            if item.get('event_id'):
                try:
                    event = Event.objects.get(
                        pk=item['event_id'],
                        user=user,
                    )
                except (Event.DoesNotExist, ValueError, TypeError):
                    raise serializers.ValidationError({
                        'carry_forward': (
                            f'Observation {index} event is not visible.'
                        )
                    })
            occurred_at = item.get('occurred_at')
            if occurred_at is not None:
                occurred_at = serializers.DateTimeField().run_validation(
                    occurred_at
                )
            validated.append({
                'id': item.get('id'),
                'target_contact': self._owned_contact(
                    item.get('target_contact_id'),
                    'carry_forward.observations.target_contact_id',
                ),
                'marker': self._visible_lookup(
                    ObservationMarker,
                    item.get('marker_id'),
                    'carry_forward.observations.marker_id',
                ),
                'body': body,
                'event': event,
                'observation_type': item.get('observation_type', ''),
                'status': item.get('status', 'current'),
                'occurred_at': occurred_at,
            })
        return validated

    @transaction.atomic
    def create(self, validated_data):
        nested = self._pop_nested(validated_data)
        reflection = Reflection.objects.create(
            user=_request_user(self),
            status=Reflection.STATUS_DRAFT,
            **validated_data,
        )
        self._save_nested(reflection, **nested)
        return reflection

    @transaction.atomic
    def update(self, instance, validated_data):
        nested = self._pop_nested(validated_data)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.revision += 1
        instance.save()
        self._save_nested(instance, partial=True, **nested)
        return instance

    def _pop_nested(self, data):
        return {
            'detail': data.pop('detail', None),
            'contacts': data.pop('contact_ids', None),
            'attachments': data.pop('attachments', None),
            'cover_media': data.pop('cover_media_asset_id', UNSET),
            'carry': data.pop('carry_forward', None),
            'expected_revision': data.pop('expected_revision', None),
        }

    def _save_nested(
        self,
        reflection,
        detail=None,
        contacts=None,
        attachments=None,
        cover_media=None,
        carry=None,
        expected_revision=None,
        partial=False,
    ):
        if detail is not None or not partial:
            self._save_detail(reflection, detail or {})
        if contacts is not None:
            self._replace_contacts(reflection, contacts)
        elif not partial and reflection.primary_contact_id:
            self._replace_contacts(reflection, [reflection.primary_contact])
        if attachments is not None:
            self._replace_attachments(reflection, attachments)
        if carry is not None:
            self._replace_carry_forward(reflection, carry)
        if cover_media is not UNSET and cover_media is None:
            if reflection.cover_attachment_id:
                reflection.cover_attachment = None
                reflection.save(update_fields=['cover_attachment'])
        elif cover_media is not UNSET:
            attachment = reflection.attachments.filter(
                media_asset=cover_media
            ).first()
            if not attachment:
                raise serializers.ValidationError({
                    'cover_media_asset_id': (
                        'Cover media must also appear in attachments.'
                    )
                })
            if attachment.is_sensitive:
                raise serializers.ValidationError({
                    'cover_media_asset_id': (
                        'Sensitive attachments cannot be used as a cover.'
                    )
                })
            if not attachment.media_asset.content_type.lower().startswith(
                'image/'
            ):
                raise serializers.ValidationError({
                    'cover_media_asset_id': (
                        'Cover media must be an image.'
                    )
                })
            reflection.cover_attachment = attachment
            reflection.save(update_fields=['cover_attachment'])

    def _save_detail(self, reflection, values):
        model = REFLECTION_DETAIL_MODELS[reflection.format]
        detail, _ = model.objects.get_or_create(reflection=reflection)
        emotions = values.pop('emotions', None)
        manifestations = values.pop('manifestations', None)
        for field, value in values.items():
            setattr(detail, field, value)
        detail.save()
        if emotions is not None:
            detail.emotions.set(emotions)
        if manifestations is not None:
            keep_ids = []
            for index, item in enumerate(manifestations):
                item_id = item.pop('id', None)
                item['display_order'] = item.get('display_order', index)
                if item_id:
                    manifestation = detail.manifestations.filter(
                        pk=item_id
                    ).first()
                    if not manifestation:
                        raise serializers.ValidationError({
                            'detail.manifestations': (
                                'Manifestation does not belong to this reflection.'
                            )
                        })
                    for field, value in item.items():
                        setattr(manifestation, field, value)
                    manifestation.save()
                else:
                    manifestation = detail.manifestations.create(**item)
                keep_ids.append(manifestation.id)
            detail.manifestations.exclude(pk__in=keep_ids).delete()

    def _replace_contacts(self, reflection, contacts):
        unique = []
        seen = set()
        if reflection.primary_contact and reflection.primary_contact not in contacts:
            contacts = [*contacts, reflection.primary_contact]
        for contact in contacts:
            if contact.id not in seen:
                seen.add(contact.id)
                unique.append(contact)
        ReflectionContact.objects.filter(reflection=reflection).delete()
        ReflectionContact.objects.bulk_create(
            ReflectionContact(
                reflection=reflection,
                contact=contact,
                display_order=index,
            )
            for index, contact in enumerate(unique)
        )

    def _replace_attachments(self, reflection, attachments):
        keep_ids = []
        for item in attachments:
            attachment, _ = ReflectionAttachment.objects.update_or_create(
                reflection=reflection,
                media_asset=item.pop('media_asset'),
                defaults=item,
            )
            keep_ids.append(attachment.id)
        stale = reflection.attachments.exclude(pk__in=keep_ids)
        stale_ids = set(stale.values_list('id', flat=True))
        if reflection.cover_attachment_id in stale_ids:
            reflection.cover_attachment = None
            reflection.save(update_fields=['cover_attachment'])
        stale.delete()
        if (
            reflection.cover_attachment_id
            and reflection.attachments.filter(
                pk=reflection.cover_attachment_id,
                is_sensitive=True,
            ).exists()
        ):
            reflection.cover_attachment = None
            reflection.save(update_fields=['cover_attachment'])

    def _replace_carry_forward(self, reflection, payload):
        if reflection.status == Reflection.STATUS_COMPLETED:
            self._assert_completed_carry_unchanged(
                reflection,
                payload,
            )
            return
        self._replace_drafts(
            reflection,
            CarryForwardFactDraft,
            payload['facts'],
            'fact_drafts',
        )
        self._replace_drafts(
            reflection,
            CarryForwardObservationDraft,
            payload['observations'],
            'observation_drafts',
        )

    def _assert_completed_carry_unchanged(self, reflection, payload):
        self._assert_drafts_unchanged(
            reflection,
            payload['facts'],
            'fact_drafts',
        )
        self._assert_drafts_unchanged(
            reflection,
            payload['observations'],
            'observation_drafts',
        )

    def _assert_drafts_unchanged(self, reflection, items, relation):
        existing = {
            str(draft.pk): draft
            for draft in getattr(reflection, relation).all()
        }
        if len(items) != len(existing):
            raise serializers.ValidationError({
                'carry_forward': (
                    'Carry-forward items cannot be added, changed, or removed '
                    'after completion.'
                )
            })
        for item in items:
            draft = existing.get(str(item.get('id') or ''))
            if not draft or any(
                getattr(draft, field) != value
                for field, value in item.items()
                if field != 'id'
            ):
                raise serializers.ValidationError({
                    'carry_forward': (
                        'Carry-forward items cannot be added, changed, or '
                        'removed after completion.'
                    )
                })

    def _replace_drafts(self, reflection, model, items, relation):
        keep_ids = []
        for item in items:
            item_id = item.pop('id', None)
            draft = (
                getattr(reflection, relation).filter(pk=item_id).first()
                if item_id
                else None
            )
            if item_id and not draft:
                raise serializers.ValidationError({
                    'carry_forward': (
                        'Carry-forward item does not belong to this reflection.'
                    )
                })
            if draft:
                if (
                    getattr(draft, 'published_fact_id', None)
                    or getattr(draft, 'published_observation_id', None)
                ):
                    raise serializers.ValidationError({
                        'carry_forward': (
                            'Published carry-forward items are immutable.'
                        )
                    })
                for field, value in item.items():
                    setattr(draft, field, value)
                draft.save()
            else:
                draft = model.objects.create(reflection=reflection, **item)
            keep_ids.append(draft.id)
        stale = getattr(reflection, relation).exclude(pk__in=keep_ids)
        if any(
            getattr(draft, 'published_fact_id', None)
            or getattr(draft, 'published_observation_id', None)
            for draft in stale
        ):
            raise serializers.ValidationError({
                'carry_forward': (
                    'Published carry-forward items are immutable.'
                )
            })
        stale.delete()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['attachments'] = [
            self._attachment_representation(instance, attachment)
            for attachment in instance.attachments.all()
        ]
        data['carry_forward'] = {
            'facts': [
                {
                    'id': draft.id,
                    'target_contact_id': draft.target_contact_id,
                    'category_id': draft.category_id,
                    'label': draft.label,
                    'detail_value': draft.detail_value,
                    'is_conversation_cue': draft.is_conversation_cue,
                    'published_fact_id': draft.published_fact_id,
                }
                for draft in instance.fact_drafts.all()
            ],
            'observations': [
                {
                    'id': draft.id,
                    'target_contact_id': draft.target_contact_id,
                    'marker_id': draft.marker_id,
                    'body': draft.body,
                    'event_id': draft.event_id,
                    'observation_type': draft.observation_type,
                    'status': draft.status,
                    'occurred_at': draft.occurred_at,
                    'published_observation_id': draft.published_observation_id,
                }
                for draft in instance.observation_drafts.all()
            ],
        }
        return data

    def _attachment_representation(self, reflection, attachment):
        media = attachment.media_asset
        media_type = media.media_type.name if media.media_type else None
        return {
            'id': attachment.id,
            'media_asset': {
                'id': media.id,
                'media_type': media_type,
                'file_url': media.file.url if media.file else '',
                'thumbnail_url': None,
                'original_filename': media.original_filename,
                'duration_seconds': None,
                'content_type': media.content_type,
                'alt_text': media.alt_text,
                'caption': media.caption,
                'created_timestamp': serializers.DateTimeField().to_representation(
                    media.created_timestamp
                ),
            },
            'is_sensitive': attachment.is_sensitive,
            'recorded_at': attachment.recorded_at,
            'display_order': attachment.display_order,
            'is_cover': reflection.cover_attachment_id == attachment.id,
        }


class HubItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    family = serializers.CharField()
    format = serializers.CharField()
    status = serializers.CharField()
    title = serializers.CharField()
    summary = serializers.CharField(allow_blank=True, max_length=160)
    event = serializers.JSONField(allow_null=True)
    primary_contact = serializers.JSONField(allow_null=True)
    occurred_at = serializers.DateTimeField(allow_null=True)
    current_step = serializers.CharField()
    progress = serializers.JSONField()
    revision = serializers.IntegerField()
    created_timestamp = serializers.DateTimeField()
    updated_timestamp = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    media_count = serializers.IntegerField()
    cover = serializers.JSONField(allow_null=True)


class LogPatternSerializer(serializers.Serializer):
    window = serializers.JSONField()
    total = serializers.IntegerField()
    by_format = serializers.DictField(
        child=serializers.IntegerField(),
    )
    episode = serializers.JSONField()
    social_energy = serializers.JSONField()
    sentiment = serializers.JSONField()


class JournalLookupSerializer(serializers.ModelSerializer):
    class Meta:
        fields = [
            'id',
            'code',
            'name',
            'icon_reference',
            'color',
            'is_system_default',
        ]
        read_only_fields = [
            'code',
            'icon_reference',
            'color',
            'is_system_default',
        ]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter a name.')
        return value


class EpisodeCategorySerializer(JournalLookupSerializer):
    class Meta(JournalLookupSerializer.Meta):
        model = EpisodeCategory


class EpisodeCharacteristicSerializer(JournalLookupSerializer):
    class Meta(JournalLookupSerializer.Meta):
        model = EpisodeCharacteristic


class EpisodeContextTagSerializer(JournalLookupSerializer):
    class Meta(JournalLookupSerializer.Meta):
        model = EpisodeContextTag


class SocialEnergyFactorSerializer(JournalLookupSerializer):
    class Meta(JournalLookupSerializer.Meta):
        model = SocialEnergyFactor


class EmotionStateSerializer(JournalLookupSerializer):
    class Meta(JournalLookupSerializer.Meta):
        model = EmotionState


class InteractionDynamicSerializer(JournalLookupSerializer):
    class Meta(JournalLookupSerializer.Meta):
        model = InteractionDynamic
