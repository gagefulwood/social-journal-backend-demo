from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    DurationField,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Sum,
    TextField,
    UUIDField,
    Value,
    When,
)
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contacts.models import Contact
from core.pagination import StandardResultsPagination
from core.permissions import IsOwner
from events.models import Event, EventChapter, EventParticipant
from lookups.models import (
    EmotionState,
    EpisodeCategory,
    EpisodeCharacteristic,
    EpisodeContextTag,
    InteractionDynamic,
    SocialEnergyFactor,
)
from media.serializers import MediaAssetListSerializer

from .models import Log, Reflection, ReflectionAttachment, ReflectionContact
from .serializers import (
    EmotionStateSerializer,
    EpisodeCategorySerializer,
    EpisodeCharacteristicSerializer,
    EpisodeContextTagSerializer,
    HubItemSerializer,
    InteractionDynamicSerializer,
    LogPatternSerializer,
    LogSerializer,
    ReflectionSerializer,
    SocialEnergyFactorSerializer,
)
from .services import (
    JOURNAL_STEPS,
    complete_journal,
    normalize_log_format_breakdown_key,
)

SOCIAL_BATTERY_SUMMARY_LABELS = {
    'reduced': 'Lower battery',
    'unchanged': 'Steady battery',
    'increased': 'Higher battery',
}
SOCIAL_MOOD_SUMMARY_LABELS = {
    'worse': 'mood lower',
    'unchanged': 'mood unchanged',
    'improved': 'mood improved',
}
SOCIAL_BEHAVIOR_SUMMARY_LABELS = {
    'quieter': 'became quieter',
    'unchanged': 'behavior unchanged',
    'more_social': 'became more social',
    'withdrew': 'withdrew',
}


class RevisionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This journal was updated elsewhere. Refresh and try again.'
    default_code = 'revision_conflict'


class CanonicalJournalViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwner]
    pagination_class = StandardResultsPagination
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset_model.objects.none()
        queryset = (
            self.queryset_model.objects.for_user(self.request.user)
            .select_related('event', 'chapter', 'primary_contact')
        )
        queryset = self._with_related(queryset)
        status_value = self.request.query_params.get('status')
        format_value = self.request.query_params.get('format')
        event_id = self.request.query_params.get('event')
        chapter_value = self.request.query_params.get('chapter')
        contact_id = self.request.query_params.get('contact')
        search = self.request.query_params.get('search')
        if status_value:
            queryset = queryset.filter(status=status_value)
        if format_value:
            queryset = queryset.filter(format=format_value)
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        if chapter_value:
            if not event_id:
                raise ValidationError({
                    'chapter': 'Use the chapter filter together with event.'
                })
            if chapter_value == 'event':
                queryset = queryset.filter(chapter__isnull=True)
            else:
                try:
                    chapter = EventChapter.objects.get(
                        pk=chapter_value,
                        event_id=event_id,
                        event__user=self.request.user,
                    )
                except (
                    EventChapter.DoesNotExist,
                    DjangoValidationError,
                    ValueError,
                    TypeError,
                ):
                    raise ValidationError({
                        'chapter': (
                            'Select a chapter in this Event owned by the '
                            'requesting user.'
                        )
                    }) from None
                queryset = queryset.filter(chapter=chapter)
        if contact_id:
            queryset = self._filter_contact(queryset, contact_id)
        if search:
            queryset = queryset.filter(title__icontains=search.strip())
        return queryset

    def _with_related(self, queryset):
        return queryset

    def _filter_contact(self, queryset, contact_id):
        return queryset.filter(primary_contact_id=contact_id)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        instance = (
            self.queryset_model.objects.for_user(request.user)
            .select_for_update()
            .get(pk=kwargs['pk'])
        )
        self.check_object_permissions(request, instance)
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data['expected_revision'] != instance.revision:
            raise RevisionConflict()
        serializer.save()
        instance = self.get_queryset().get(pk=instance.pk)
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def complete(self, request, *args, **kwargs):
        instance = (
            self.queryset_model.objects.for_user(request.user)
            .select_for_update()
            .get(pk=kwargs['pk'])
        )
        self.check_object_permissions(request, instance)
        if instance.status == instance.STATUS_COMPLETED:
            return Response(self.get_serializer(instance).data)
        expected_revision = request.data.get('expected_revision')
        if expected_revision is None:
            raise ValidationError({
                'expected_revision': 'This field is required.'
            })
        try:
            expected_revision = int(expected_revision)
        except (TypeError, ValueError):
            raise ValidationError({
                'expected_revision': 'Enter a valid revision number.'
            })
        if expected_revision != instance.revision:
            raise RevisionConflict()
        complete_journal(instance)
        instance = self.get_queryset().get(pk=instance.pk)
        return Response(self.get_serializer(instance).data)


class LogViewSet(CanonicalJournalViewSet):
    queryset_model = Log
    serializer_class = LogSerializer

    def _with_related(self, queryset):
        return queryset.select_related(
            'episode_detail__category',
            'social_energy_detail',
            'sentiment_detail__before_state',
            'sentiment_detail__after_state',
        ).prefetch_related(
            'tags',
            'episode_detail__characteristics',
            'episode_detail__context_tags',
            'social_energy_detail__factors',
            'sentiment_detail__dynamics',
        )


class ReflectionViewSet(CanonicalJournalViewSet):
    queryset_model = Reflection
    serializer_class = ReflectionSerializer

    def _with_related(self, queryset):
        return queryset.select_related(
            'cover_attachment__media_asset__media_type',
            'interaction_detail',
            'moment_detail',
            'emotional_detail',
            'free_detail',
        ).prefetch_related(
            'contacts',
            'attachments__media_asset__media_type',
            'emotional_detail__emotions',
            'emotional_detail__manifestations',
            'fact_drafts',
            'observation_drafts',
        )

    def _filter_contact(self, queryset, contact_id):
        return queryset.filter(
            Q(primary_contact_id=contact_id) | Q(contacts__id=contact_id)
        ).distinct()


class JournalLookupViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset_model.objects.none()
        return self.queryset_model.objects.for_user(self.request.user).order_by(
            '-is_system_default',
            'name',
        )

    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            is_system_default=False,
            code='',
        )


class EpisodeCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EpisodeCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return EpisodeCategory.objects.none()
        return EpisodeCategory.objects.for_user(self.request.user).order_by('name')


class EpisodeCharacteristicViewSet(JournalLookupViewSet):
    queryset_model = EpisodeCharacteristic
    serializer_class = EpisodeCharacteristicSerializer


class EpisodeContextTagViewSet(JournalLookupViewSet):
    queryset_model = EpisodeContextTag
    serializer_class = EpisodeContextTagSerializer


class SocialEnergyFactorViewSet(JournalLookupViewSet):
    queryset_model = SocialEnergyFactor
    serializer_class = SocialEnergyFactorSerializer


class EmotionStateViewSet(JournalLookupViewSet):
    queryset_model = EmotionState
    serializer_class = EmotionStateSerializer


class InteractionDynamicViewSet(JournalLookupViewSet):
    queryset_model = InteractionDynamic
    serializer_class = InteractionDynamicSerializer


class JournalFeedView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination
    serializer_class = HubItemSerializer
    http_method_names = ['get', 'head', 'options']

    columns = [
        'id',
        'family',
        'format',
        'status',
        'title',
        'summary_primary',
        'summary_secondary',
        'summary_tertiary',
        'event_id',
        'event_title',
        'event_start_timestamp',
        'event_end_timestamp',
        'event_location',
        'chapter_id',
        'chapter_title',
        'chapter_position',
        'primary_contact_id',
        'primary_first_name',
        'primary_last_name',
        'relation_source',
        'occurred_at',
        'current_step',
        'revision',
        'created_timestamp',
        'updated_timestamp',
        'completed_at',
        'media_count',
        'cover_attachment_id',
    ]

    def get(self, request, *args, **kwargs):
        queryset = self._combined_queryset(request)
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        items = self._hydrate_rows(rows)
        serializer = self.get_serializer(items, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def _combined_queryset(self, request):
        families = self._families(request)
        logs = Log.objects.for_user(request.user)
        reflections = Reflection.objects.for_user(request.user)
        logs, reflections = self._filter_querysets(request, logs, reflections)
        querysets = []
        if 'log' in families:
            querysets.append(self._log_values(logs))
        if 'reflection' in families:
            querysets.append(self._reflection_values(reflections))
        queryset = querysets[0]
        if len(querysets) == 2:
            queryset = queryset.union(querysets[1], all=True)
        ordering = request.query_params.get('ordering', '-updated_timestamp')
        allowed_ordering = {
            'updated_timestamp',
            '-updated_timestamp',
            'occurred_at',
            '-occurred_at',
        }
        if ordering not in allowed_ordering:
            raise ValidationError({
                'ordering': (
                    'Use updated_timestamp, -updated_timestamp, '
                    'occurred_at, or -occurred_at.'
                )
            })
        return queryset.order_by(
            ordering,
            '-created_timestamp',
            '-id',
            'family',
        )

    def _families(self, request):
        raw = request.query_params.get('family')
        if not raw:
            return {'log', 'reflection'}
        families = {value.strip() for value in raw.split(',') if value.strip()}
        if not families or families - {'log', 'reflection'}:
            raise ValidationError({
                'family': 'Use log, reflection, or a comma-separated pair.'
            })
        return families

    def _filter_querysets(self, request, logs, reflections):
        status_value = request.query_params.get('status')
        format_value = request.query_params.get('format')
        search = request.query_params.get('search')
        event_id = request.query_params.get('event')
        chapter_value = request.query_params.get('chapter')
        contact_id = request.query_params.get('contact')
        related_contact_id = self._positive_integer_param(
            request,
            'related_contact',
        )
        if contact_id and related_contact_id is not None:
            raise ValidationError({
                'related_contact': (
                    'Use contact or related_contact, not both.'
                )
            })
        occurred_after = self._datetime_param(request, 'occurred_after')
        occurred_before = self._datetime_param(request, 'occurred_before')
        if status_value:
            logs = logs.filter(status=status_value)
            reflections = reflections.filter(status=status_value)
        if format_value:
            logs = logs.filter(format=format_value)
            reflections = reflections.filter(format=format_value)
        if search:
            search_value = search.strip()
            if search_value:
                logs = logs.filter(self._log_search_query(search_value))
                reflections = reflections.filter(
                    self._reflection_search_query(search_value)
                )
        if event_id:
            logs = logs.filter(event_id=event_id)
            reflections = reflections.filter(event_id=event_id)
        if chapter_value:
            if not event_id:
                raise ValidationError({
                    'chapter': 'Use the chapter filter together with event.'
                })
            if not Event.objects.filter(
                pk=event_id,
                user=request.user,
            ).exists():
                raise ValidationError({
                    'event': 'Select an Event owned by the requesting user.'
                })
            if chapter_value == 'event':
                logs = logs.filter(chapter__isnull=True)
                reflections = reflections.filter(chapter__isnull=True)
            else:
                try:
                    chapter = EventChapter.objects.get(
                        pk=chapter_value,
                        event_id=event_id,
                        event__user=request.user,
                    )
                except (
                    EventChapter.DoesNotExist,
                    DjangoValidationError,
                    ValueError,
                    TypeError,
                ):
                    raise ValidationError({
                        'chapter': (
                            'Select a chapter in this Event owned by the '
                            'requesting user.'
                        )
                    }) from None
                logs = logs.filter(chapter=chapter)
                reflections = reflections.filter(chapter=chapter)
        if contact_id:
            logs = logs.filter(primary_contact_id=contact_id)
            reflections = reflections.filter(
                Q(primary_contact_id=contact_id) | Q(contacts__id=contact_id)
            ).distinct()
        if related_contact_id is not None:
            logs = self._with_related_contact_matches(
                logs,
                request.user,
                related_contact_id,
                reflection=False,
            )
            reflections = self._with_related_contact_matches(
                reflections,
                request.user,
                related_contact_id,
                reflection=True,
            )
        else:
            logs = logs.annotate(
                relation_source=Value(
                    None,
                    output_field=CharField(max_length=6),
                ),
            )
            reflections = reflections.annotate(
                relation_source=Value(
                    None,
                    output_field=CharField(max_length=6),
                ),
            )
        if occurred_after:
            logs = logs.filter(occurred_at__gte=occurred_after)
            reflections = reflections.filter(occurred_at__gte=occurred_after)
        if occurred_before:
            logs = logs.filter(occurred_at__lte=occurred_before)
            reflections = reflections.filter(occurred_at__lte=occurred_before)
        return logs, reflections

    def _with_related_contact_matches(
        self,
        queryset,
        user,
        contact_id,
        *,
        reflection,
    ):
        direct_matches = [
            When(primary_contact_id=contact_id, then=Value(True)),
        ]
        if reflection:
            direct_matches.append(
                When(
                    Exists(
                        ReflectionContact.objects.filter(
                            reflection_id=OuterRef('pk'),
                            contact_id=contact_id,
                        )
                    ),
                    then=Value(True),
                ),
            )
        return queryset.alias(
            _related_contact_visible=Exists(
                Contact.objects.for_user(user).filter(pk=contact_id)
            ),
            _direct_contact_match=Case(
                *direct_matches,
                default=Value(False),
                output_field=BooleanField(),
            ),
            _event_contact_match=Exists(
                EventParticipant.objects.filter(
                    event_id=OuterRef('event_id'),
                    event__user=user,
                    contact_id=contact_id,
                )
            ),
        ).filter(
            _related_contact_visible=True,
        ).filter(
            Q(_direct_contact_match=True) | Q(_event_contact_match=True)
        ).annotate(
            relation_source=Case(
                When(
                    _direct_contact_match=True,
                    _event_contact_match=True,
                    then=Value('both'),
                ),
                When(
                    _direct_contact_match=True,
                    then=Value('direct'),
                ),
                When(
                    _event_contact_match=True,
                    then=Value('event'),
                ),
                default=Value(None),
                output_field=CharField(max_length=6),
            ),
        )

    def _log_search_query(self, value):
        social_fields = (
            Q(social_energy_detail__battery_effect__icontains=value)
            | Q(social_energy_detail__mood_shift__icontains=value)
            | Q(social_energy_detail__behavioral_effect__icontains=value)
            | Q(
                social_energy_detail__battery_effect__in=(
                    self._summary_label_codes(
                        value,
                        SOCIAL_BATTERY_SUMMARY_LABELS,
                    )
                )
            )
            | Q(
                social_energy_detail__mood_shift__in=(
                    self._summary_label_codes(
                        value,
                        SOCIAL_MOOD_SUMMARY_LABELS,
                    )
                )
            )
            | Q(
                social_energy_detail__behavioral_effect__in=(
                    self._summary_label_codes(
                        value,
                        SOCIAL_BEHAVIOR_SUMMARY_LABELS,
                    )
                )
            )
        )
        return (
            Q(title__icontains=value)
            | (
                Q(format=Log.FORMAT_EPISODE)
                & Q(episode_detail__category__name__icontains=value)
            )
            | (Q(format=Log.FORMAT_SOCIAL_ENERGY) & social_fields)
            | (
                Q(format=Log.FORMAT_SENTIMENT)
                & (
                    Q(sentiment_detail__before_state__name__icontains=value)
                    | Q(sentiment_detail__after_state__name__icontains=value)
                )
            )
        )

    def _reflection_search_query(self, value):
        return (
            Q(title__icontains=value)
            | (
                Q(format=Reflection.FORMAT_INTERACTION)
                & Q(interaction_detail__topic_or_activity__icontains=value)
            )
            | (
                Q(format=Reflection.FORMAT_MOMENT)
                & Q(moment_detail__focus_moment__icontains=value)
            )
            | (
                Q(format=Reflection.FORMAT_EMOTIONAL)
                & Q(emotional_detail__situation__icontains=value)
            )
        )

    def _summary_label_codes(self, value, labels):
        normalized = value.casefold()
        return [
            code
            for code, label in labels.items()
            if normalized in label.casefold()
        ]

    def _datetime_param(self, request, name):
        value = request.query_params.get(name)
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            raise ValidationError({name: 'Enter a valid ISO 8601 timestamp.'})
        return parsed

    def _positive_integer_param(self, request, name):
        value = request.query_params.get(name)
        if not value:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise ValidationError({name: 'Enter a valid positive integer.'})
        if parsed <= 0:
            raise ValidationError({name: 'Enter a valid positive integer.'})
        return parsed

    def _common_annotations(self, family):
        return {
            'family': Value(family, output_field=CharField()),
            'event_title': F('event__title'),
            'event_start_timestamp': F('event__event_timestamp'),
            'event_end_timestamp': F('event__end_timestamp'),
            'event_location': F('event__location_label'),
            'chapter_title': F('chapter__title'),
            'chapter_position': F('chapter__position'),
            'primary_first_name': F('primary_contact__first_name'),
            'primary_last_name': F('primary_contact__last_name'),
        }

    def _log_values(self, queryset):
        return (
            queryset.annotate(
                **self._common_annotations('log'),
                summary_primary=Case(
                    When(
                        format=Log.FORMAT_EPISODE,
                        then=F('episode_detail__category__name'),
                    ),
                    When(
                        format=Log.FORMAT_SOCIAL_ENERGY,
                        then=F('social_energy_detail__battery_effect'),
                    ),
                    When(
                        format=Log.FORMAT_SENTIMENT,
                        then=F('sentiment_detail__before_state__name'),
                    ),
                    default=Value(''),
                    output_field=TextField(),
                ),
                summary_secondary=Case(
                    When(
                        format=Log.FORMAT_SOCIAL_ENERGY,
                        then=F('social_energy_detail__mood_shift'),
                    ),
                    When(
                        format=Log.FORMAT_SENTIMENT,
                        then=F('sentiment_detail__after_state__name'),
                    ),
                    default=Value(''),
                    output_field=TextField(),
                ),
                summary_tertiary=Case(
                    When(
                        format=Log.FORMAT_SOCIAL_ENERGY,
                        then=F('social_energy_detail__behavioral_effect'),
                    ),
                    default=Value(''),
                    output_field=TextField(),
                ),
                media_count=Value(0, output_field=IntegerField()),
                cover_attachment_id=Value(None, output_field=UUIDField()),
            )
            .values(*self.columns)
        )

    def _reflection_values(self, queryset):
        return (
            queryset.annotate(
                **self._common_annotations('reflection'),
                summary_primary=Case(
                    When(
                        format=Reflection.FORMAT_INTERACTION,
                        then=F('interaction_detail__topic_or_activity'),
                    ),
                    When(
                        format=Reflection.FORMAT_MOMENT,
                        then=F('moment_detail__focus_moment'),
                    ),
                    When(
                        format=Reflection.FORMAT_EMOTIONAL,
                        then=F('emotional_detail__situation'),
                    ),
                    default=Value(''),
                    output_field=TextField(),
                ),
                summary_secondary=Value('', output_field=TextField()),
                summary_tertiary=Value('', output_field=TextField()),
                media_count=Count('attachments', distinct=True),
            )
            .values(*self.columns)
        )

    def _hydrate_rows(self, rows):
        cover_ids = [
            row['cover_attachment_id']
            for row in rows
            if row['cover_attachment_id']
        ]
        covers = {
            attachment.id: attachment
            for attachment in ReflectionAttachment.objects.filter(
                id__in=cover_ids,
                is_sensitive=False,
                media_asset__content_type__istartswith='image/',
            ).select_related('media_asset__media_type')
        }
        return [self._hub_item(row, covers) for row in rows]

    def _hub_item(self, row, covers):
        event = None
        if row['event_id']:
            event = {
                'id': row['event_id'],
                'title': row['event_title'],
                'start_timestamp': row['event_start_timestamp'],
                'end_timestamp': row['event_end_timestamp'],
                'location': row['event_location'] or None,
            }
        primary_contact = None
        if row['primary_contact_id']:
            display_name = ' '.join(
                value
                for value in (
                    row['primary_first_name'],
                    row['primary_last_name'],
                )
                if value
            )
            primary_contact = {
                'id': row['primary_contact_id'],
                'display_name': display_name,
            }
        chapter = None
        if row['chapter_id']:
            chapter = {
                'id': row['chapter_id'],
                'title': row['chapter_title'],
                'position': row['chapter_position'],
            }
        steps = JOURNAL_STEPS.get(row['format'], ['writing'])
        total_steps = len(steps)
        if row['status'] == 'completed':
            completed_steps = total_steps
        elif row['current_step'] in steps:
            completed_steps = steps.index(row['current_step'])
        else:
            completed_steps = 0
        cover = self._cover_summary(
            covers.get(row['cover_attachment_id'])
        )
        return {
            'id': row['id'],
            'family': row['family'],
            'format': row['format'],
            'status': row['status'],
            'title': row['title'],
            'summary': self._summary_for(row),
            'event': event,
            'chapter': chapter,
            'primary_contact': primary_contact,
            'relation_source': row['relation_source'],
            'occurred_at': row['occurred_at'],
            'current_step': row['current_step'],
            'progress': {
                'current_step': row['current_step'],
                'completed_steps': completed_steps,
                'total_steps': total_steps,
                'percent': (
                    round((completed_steps / total_steps) * 100)
                    if total_steps
                    else 0
                ),
            },
            'revision': row['revision'],
            'created_timestamp': row['created_timestamp'],
            'updated_timestamp': row['updated_timestamp'],
            'completed_at': row['completed_at'],
            'media_count': row['media_count'],
            'cover': cover,
        }

    def _summary_for(self, row):
        primary = row['summary_primary'] or ''
        secondary = row['summary_secondary'] or ''
        tertiary = row['summary_tertiary'] or ''
        journal_format = row['format']
        if journal_format == Log.FORMAT_EPISODE:
            summary = f'Category: {primary}' if primary else ''
        elif journal_format == Log.FORMAT_SOCIAL_ENERGY:
            summary = ' · '.join(
                part
                for part in (
                    SOCIAL_BATTERY_SUMMARY_LABELS.get(primary, ''),
                    SOCIAL_MOOD_SUMMARY_LABELS.get(secondary, ''),
                    SOCIAL_BEHAVIOR_SUMMARY_LABELS.get(tertiary, ''),
                )
                if part
            )
        elif journal_format == Log.FORMAT_SENTIMENT:
            if primary and secondary:
                summary = f'{primary} → {secondary}'
            else:
                summary = primary or secondary
        elif journal_format == Reflection.FORMAT_INTERACTION:
            summary = f'Topic: {primary}' if primary else ''
        elif journal_format == Reflection.FORMAT_MOMENT:
            summary = f'Focus: {primary}' if primary else ''
        elif journal_format == Reflection.FORMAT_EMOTIONAL:
            summary = f'Feeling context: {primary}' if primary else ''
        else:
            summary = ''
        return self._bounded_summary(summary)

    def _bounded_summary(self, value):
        summary = ' '.join(str(value or '').split())
        if len(summary) <= 160:
            return summary
        return f'{summary[:159].rstrip()}…'

    def _cover_summary(self, attachment):
        if (
            attachment is None
            or attachment.is_sensitive
            or not attachment.media_asset.content_type.lower().startswith(
                'image/'
            )
        ):
            return None
        media = attachment.media_asset
        media_representation = MediaAssetListSerializer(
            media,
            context=self.get_serializer_context(),
        ).data
        return {
            'attachment_id': attachment.id,
            'media_asset_id': media.id,
            'media_type': media.media_type.name if media.media_type else None,
            'file_url': media_representation['content_url'],
            'alt_text': media.alt_text,
        }


class LogPatternView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogPatternSerializer
    http_method_names = ['get', 'head', 'options']

    def get(self, request, *args, **kwargs):
        try:
            days = int(request.query_params.get('days', 30))
        except (TypeError, ValueError):
            raise ValidationError({'days': 'Enter a whole number.'})
        if days < 1 or days > 365:
            raise ValidationError({'days': 'Use a value from 1 through 365.'})
        end = timezone.now()
        start = end - timedelta(days=days)
        queryset = Log.objects.for_user(request.user).filter(
            status=Log.STATUS_COMPLETED,
            occurred_at__gte=start,
            occurred_at__lte=end,
        )
        format_value = request.query_params.get('format')
        if format_value:
            queryset = queryset.filter(format=format_value)
        by_format = {}
        for row in queryset.values('format').annotate(count=Count('id')):
            key = normalize_log_format_breakdown_key(row['format'])
            by_format[key] = by_format.get(key, 0) + row['count']
        episode_queryset = queryset.filter(format=Log.FORMAT_EPISODE)
        duration = episode_queryset.filter(
            episode_detail__ended_at__isnull=False,
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('episode_detail__ended_at') - F('occurred_at'),
                    output_field=DurationField(),
                )
            )
        )['total']
        characteristic_counts = [
            {
                'id': row['episode_detail__characteristics__id'],
                'code': row['episode_detail__characteristics__code'],
                'name': row['episode_detail__characteristics__name'],
                'count': row['count'],
            }
            for row in episode_queryset.values(
                'episode_detail__characteristics__id',
                'episode_detail__characteristics__code',
                'episode_detail__characteristics__name',
            )
            .exclude(episode_detail__characteristics__isnull=True)
            .annotate(count=Count('id'))
            .order_by('-count', 'episode_detail__characteristics__name')
        ]
        social_effects = [
            {
                'battery_effect': row[
                    'social_energy_detail__battery_effect'
                ],
                'mood_shift': row['social_energy_detail__mood_shift'],
                'behavioral_effect': row[
                    'social_energy_detail__behavioral_effect'
                ],
                'count': row['count'],
            }
            for row in queryset.filter(format=Log.FORMAT_SOCIAL_ENERGY)
            .values(
                'social_energy_detail__battery_effect',
                'social_energy_detail__mood_shift',
                'social_energy_detail__behavioral_effect',
            )
            .annotate(count=Count('id'))
            .order_by('-count')
        ]
        sentiment_shifts = [
            {
                'before_state': row['sentiment_detail__before_state__code'],
                'after_state': row['sentiment_detail__after_state__code'],
                'overall_exchange': row[
                    'sentiment_detail__overall_exchange'
                ],
                'count': row['count'],
            }
            for row in queryset.filter(format=Log.FORMAT_SENTIMENT)
            .values(
                'sentiment_detail__before_state__code',
                'sentiment_detail__after_state__code',
                'sentiment_detail__overall_exchange',
            )
            .annotate(count=Count('id'))
            .order_by('-count')
        ]
        return Response({
            'window': {
                'days': days,
                'from': start,
                'to': end,
            },
            'total': queryset.count(),
            'by_format': by_format,
            'episode': {
                'count': by_format.get(Log.FORMAT_EPISODE, 0),
                'total_duration_minutes': (
                    round(duration.total_seconds() / 60)
                    if duration
                    else 0
                ),
                'characteristics': characteristic_counts,
            },
            'social_energy': {
                'count': by_format.get(Log.FORMAT_SOCIAL_ENERGY, 0),
                'effects': social_effects,
            },
            'sentiment': {
                'count': by_format.get(Log.FORMAT_SENTIMENT, 0),
                'shifts': sentiment_shifts,
            },
        })
