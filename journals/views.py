from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
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
    Subquery,
    Sum,
    TextField,
    UUIDField,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.urls import reverse
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
from media.signing import sign_media_content

from .models import Log, Reflection, ReflectionContact
from .serializers import (
    EmotionStateSerializer,
    EpisodeCategorySerializer,
    EpisodeCharacteristicSerializer,
    EpisodeContextTagSerializer,
    HubItemSerializer,
    InteractionDynamicSerializer,
    ContactJournalSummarySerializer,
    JournalHubSummarySerializer,
    JournalFilterOptionsSerializer,
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


class PrecountedQuerySequence:
    """Let DRF paginate a queryset without recounting its UNION."""

    ordered = True

    def __init__(self, queryset, count):
        self.queryset = queryset
        self._count = count

    def count(self):
        return self._count

    def __getitem__(self, key):
        return self.queryset[key]


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
        contact_link = Exists(
            ReflectionContact.objects.filter(
                reflection_id=OuterRef('pk'),
                contact_id=contact_id,
            )
        )
        return queryset.filter(
            Q(primary_contact_id=contact_id) | Q(contact_link)
        )


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
        'relation_direct',
        'relation_event',
        'occurred_at',
        'current_step',
        'revision',
        'created_timestamp',
        'updated_timestamp',
        'completed_at',
        'media_count',
        'cover_attachment_id',
        'cover_asset_id',
        'cover_asset_user_id',
        'cover_media_type_name',
        'cover_content_type',
        'cover_alt_text',
        'cover_is_sensitive',
    ]
    identity_columns = [
        'id',
        'family',
        'occurred_at',
        'updated_timestamp',
        'created_timestamp',
    ]

    def get(self, request, *args, **kwargs):
        params = request.query_params
        (
            families,
            ordering,
            logs,
            reflections,
            related_contact_id,
            related_contact_visible,
        ) = self._prepare_query(
            request.user,
            params,
        )
        if related_contact_id is not None and not related_contact_visible:
            total_count = 0
        else:
            counts = self._count_querysets(
                request.user,
                logs,
                reflections,
                families,
            )
            total_count = counts['log'] + counts['reflection']
        queryset = self._identity_queryset(
            logs,
            reflections,
            families,
            ordering,
        )
        page = self.paginate_queryset(
            PrecountedQuerySequence(queryset, total_count)
        )
        rows = page if page is not None else list(queryset)
        items = self._hydrate_rows(rows, related_contact_id)
        serializer = self.get_serializer(items, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def _prepare_query(
        self,
        user,
        params,
        *,
        validated_related_contact_id=None,
    ):
        families = self._families(params)
        ordering = self._ordering(params)
        logs = Log.objects.for_user(user)
        reflections = Reflection.objects.for_user(user)
        (
            logs,
            reflections,
            related_contact_id,
            related_contact_visible,
        ) = self._filter_querysets(
            user,
            params,
            logs,
            reflections,
            validated_related_contact_id=validated_related_contact_id,
        )
        return (
            families,
            ordering,
            logs,
            reflections,
            related_contact_id,
            related_contact_visible,
        )

    def _feed_slice(
        self,
        user,
        params,
        *,
        limit,
        validated_related_contact_id=None,
    ):
        (
            families,
            ordering,
            logs,
            reflections,
            related_contact_id,
            related_contact_visible,
        ) = self._prepare_query(
            user,
            params,
            validated_related_contact_id=validated_related_contact_id,
        )
        if related_contact_id is not None and not related_contact_visible:
            return {'log': 0, 'reflection': 0}, []
        counts = self._count_querysets(
            user,
            logs,
            reflections,
            families,
        )
        identities = list(
            self._identity_queryset(
                logs,
                reflections,
                families,
                ordering,
            )[:limit]
        )
        return counts, self._hydrate_rows(
            identities,
            related_contact_id,
        )

    def _identity_queryset(self, logs, reflections, families, ordering):
        querysets = []
        if 'log' in families:
            querysets.append(self._identity_values(logs, 'log'))
        if 'reflection' in families:
            querysets.append(self._identity_values(reflections, 'reflection'))
        queryset = querysets[0]
        if len(querysets) == 2:
            queryset = queryset.union(querysets[1], all=True)
        return queryset.order_by(
            ordering,
            '-created_timestamp',
            '-id',
            'family',
        )

    def _identity_values(self, queryset, family):
        return queryset.order_by().annotate(
            family=Value(family, output_field=CharField()),
        ).values(*self.identity_columns)

    def _ordering(self, params):
        ordering = params.get('ordering', '-updated_timestamp')
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
        return ordering

    def _families(self, params):
        raw = params.get('family')
        if not raw:
            return {'log', 'reflection'}
        families = {value.strip() for value in raw.split(',') if value.strip()}
        if not families or families - {'log', 'reflection'}:
            raise ValidationError({
                'family': 'Use log, reflection, or a comma-separated pair.'
            })
        return families

    def _filter_querysets(
        self,
        user,
        params,
        logs,
        reflections,
        *,
        validated_related_contact_id=None,
    ):
        status_value = params.get('status')
        format_value = params.get('format')
        search = params.get('search')
        event_id = params.get('event')
        chapter_value = params.get('chapter')
        contact_id = params.get('contact')
        related_contact_id = self._positive_integer_param(
            params,
            'related_contact',
        )
        if contact_id and related_contact_id is not None:
            raise ValidationError({
                'related_contact': (
                    'Use contact or related_contact, not both.'
                )
            })
        occurred_after = self._datetime_param(params, 'occurred_after')
        occurred_before = self._datetime_param(params, 'occurred_before')
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
                user=user,
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
                        event__user=user,
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
            contact_link = Exists(
                ReflectionContact.objects.filter(
                    reflection_id=OuterRef('pk'),
                    contact_id=contact_id,
                )
            )
            reflections = reflections.filter(
                Q(primary_contact_id=contact_id) | Q(contact_link)
            )
        related_contact_visible = True
        if related_contact_id is not None:
            related_contact_visible = (
                related_contact_id == validated_related_contact_id
                or Contact.objects.for_user(user).filter(
                    pk=related_contact_id,
                ).exists()
            )
            if related_contact_visible:
                logs, reflections = self._with_related_contact_matches(
                    logs,
                    reflections,
                    user,
                    related_contact_id,
                )
            else:
                logs = logs.none()
                reflections = reflections.none()
        if occurred_after:
            logs = logs.filter(occurred_at__gte=occurred_after)
            reflections = reflections.filter(occurred_at__gte=occurred_after)
        if occurred_before:
            logs = logs.filter(occurred_at__lte=occurred_before)
            reflections = reflections.filter(occurred_at__lte=occurred_before)
        return (
            logs,
            reflections,
            related_contact_id,
            related_contact_visible,
        )

    def _with_related_contact_matches(
        self,
        logs,
        reflections,
        user,
        contact_id,
    ):
        related_event_ids = EventParticipant.objects.filter(
            event__user=user,
            contact_id=contact_id,
        ).values('event_id')
        logs = logs.filter(
            Q(primary_contact_id=contact_id)
            | Q(event_id__in=Subquery(related_event_ids))
        )
        contact_link = Exists(
            ReflectionContact.objects.filter(
                reflection_id=OuterRef('pk'),
                contact_id=contact_id,
            )
        )
        reflections = reflections.filter(
            Q(primary_contact_id=contact_id)
            | Q(contact_link)
            | Q(event_id__in=Subquery(related_event_ids))
        )
        return logs, reflections

    def _count_querysets(
        self,
        user,
        logs,
        reflections,
        families,
    ):
        def count_subquery(queryset):
            return (
                queryset.order_by()
                .values('user_id')
                .annotate(total=Count('pk'))
                .values('total')[:1]
            )

        annotations = {
            'log_total': (
                Coalesce(
                    Subquery(
                        count_subquery(logs),
                        output_field=IntegerField(),
                    ),
                    Value(0),
                )
                if 'log' in families
                else Value(0, output_field=IntegerField())
            ),
            'reflection_total': (
                Coalesce(
                    Subquery(
                        count_subquery(reflections),
                        output_field=IntegerField(),
                    ),
                    Value(0),
                )
                if 'reflection' in families
                else Value(0, output_field=IntegerField())
            ),
        }
        totals = (
            get_user_model()
            .objects.filter(pk=user.pk)
            .annotate(**annotations)
            .values('log_total', 'reflection_total')
            .get()
        )
        return {
            'log': totals['log_total'],
            'reflection': totals['reflection_total'],
        }

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

    def _datetime_param(self, params, name):
        value = params.get(name)
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            raise ValidationError({name: 'Enter a valid ISO 8601 timestamp.'})
        return parsed

    def _positive_integer_param(self, params, name):
        value = params.get(name)
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

    def _relation_annotations(self, contact_id, *, reflection):
        if contact_id is None:
            return {
                'relation_direct': Value(
                    False,
                    output_field=BooleanField(),
                ),
                'relation_event': Value(
                    False,
                    output_field=BooleanField(),
                ),
            }
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
        return {
            'relation_direct': Case(
                *direct_matches,
                default=Value(False),
                output_field=BooleanField(),
            ),
            'relation_event': Exists(
                EventParticipant.objects.filter(
                    event_id=OuterRef('event_id'),
                    event__user=self.request.user,
                    contact_id=contact_id,
                )
            ),
        }

    def _log_values(self, queryset, related_contact_id):
        return (
            queryset.annotate(
                **self._common_annotations('log'),
                **self._relation_annotations(
                    related_contact_id,
                    reflection=False,
                ),
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
                cover_asset_id=Value(None, output_field=IntegerField()),
                cover_asset_user_id=Value(
                    None,
                    output_field=IntegerField(),
                ),
                cover_media_type_name=Value(
                    None,
                    output_field=CharField(),
                ),
                cover_content_type=Value('', output_field=CharField()),
                cover_alt_text=Value('', output_field=TextField()),
                cover_is_sensitive=Value(
                    False,
                    output_field=BooleanField(),
                ),
            )
            .values(*self.columns)
        )

    def _reflection_values(self, queryset, related_contact_id):
        return (
            queryset.annotate(
                **self._common_annotations('reflection'),
                **self._relation_annotations(
                    related_contact_id,
                    reflection=True,
                ),
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
                cover_asset_id=F('cover_attachment__media_asset_id'),
                cover_asset_user_id=F(
                    'cover_attachment__media_asset__user_id'
                ),
                cover_media_type_name=F(
                    'cover_attachment__media_asset__media_type__name'
                ),
                cover_content_type=F(
                    'cover_attachment__media_asset__content_type'
                ),
                cover_alt_text=F(
                    'cover_attachment__media_asset__alt_text'
                ),
                cover_is_sensitive=F('cover_attachment__is_sensitive'),
            )
            .values(*self.columns)
        )

    def _hydrate_rows(self, rows, related_contact_id):
        identities = list(rows)
        log_ids = [
            row['id'] for row in identities if row['family'] == 'log'
        ]
        reflection_ids = [
            row['id'] for row in identities if row['family'] == 'reflection'
        ]
        hydrated = {}
        if log_ids:
            queryset = Log.objects.for_user(self.request.user).filter(
                pk__in=log_ids
            )
            for row in self._log_values(queryset, related_contact_id):
                hydrated[('log', row['id'])] = row
        if reflection_ids:
            queryset = Reflection.objects.for_user(self.request.user).filter(
                pk__in=reflection_ids
            )
            for row in self._reflection_values(
                queryset,
                related_contact_id,
            ):
                hydrated[('reflection', row['id'])] = row
        return [
            self._hub_item(hydrated[(row['family'], row['id'])])
            for row in identities
            if (row['family'], row['id']) in hydrated
        ]

    def _hub_item(self, row):
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
        cover = self._cover_summary(row)
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
            'relation_source': self._relation_source(row),
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

    def _relation_source(self, row):
        if row['relation_direct'] and row['relation_event']:
            return 'both'
        if row['relation_direct']:
            return 'direct'
        if row['relation_event']:
            return 'event'
        return None

    def _cover_summary(self, row):
        if (
            not row['cover_attachment_id']
            or not row['cover_asset_id']
            or row['cover_is_sensitive']
            or row['cover_asset_user_id'] != self.request.user.pk
            or not (row['cover_content_type'] or '').lower().startswith('image/')
        ):
            return None
        asset = SimpleNamespace(
            pk=row['cover_asset_id'],
            user_id=row['cover_asset_user_id'],
        )
        path = reverse('media-content', args=[row['cover_asset_id']])
        path = f'{path}?{urlencode({"token": sign_media_content(asset)})}'
        return {
            'attachment_id': row['cover_attachment_id'],
            'media_asset_id': row['cover_asset_id'],
            'media_type': row['cover_media_type_name'],
            'file_url': self.request.build_absolute_uri(path),
            'alt_text': row['cover_alt_text'],
        }


class JournalHubSummaryView(JournalFeedView):
    serializer_class = JournalHubSummarySerializer

    def get(self, request, *args, **kwargs):
        counts, drafts = self._feed_slice(
            request.user,
            {
                'status': Log.STATUS_DRAFT,
                'ordering': '-updated_timestamp',
            },
            limit=10,
        )
        payload = {
            'draft_count': counts['log'] + counts['reflection'],
            'drafts': drafts,
        }
        return Response(self.get_serializer(payload).data)


class ContactJournalSummaryView(JournalFeedView):
    serializer_class = ContactJournalSummarySerializer

    def get(self, request, contact_id, *args, **kwargs):
        contact = get_object_or_404(
            Contact.objects.for_user(request.user),
            pk=contact_id,
        )
        completed_counts, completed = self._feed_slice(
            request.user,
            {
                'related_contact': contact.id,
                'status': Log.STATUS_COMPLETED,
                'ordering': '-occurred_at',
            },
            limit=1,
            validated_related_contact_id=contact.id,
        )
        draft_counts, drafts = self._feed_slice(
            request.user,
            {
                'related_contact': contact.id,
                'status': Log.STATUS_DRAFT,
                'ordering': '-updated_timestamp',
            },
            limit=2,
            validated_related_contact_id=contact.id,
        )
        payload = {
            'completed_count': (
                completed_counts['log'] + completed_counts['reflection']
            ),
            'log_count': completed_counts['log'],
            'reflection_count': completed_counts['reflection'],
            'draft_count': draft_counts['log'] + draft_counts['reflection'],
            'latest_completed': completed[0] if completed else None,
            'drafts': drafts,
        }
        return Response(self.get_serializer(payload).data)


class JournalFilterOptionsView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = JournalFilterOptionsSerializer
    http_method_names = ['get', 'head', 'options']

    def get(self, request, *args, **kwargs):
        limit = self._limit(request)
        contact_search = request.query_params.get('contact_search', '').strip()
        event_search = request.query_params.get('event_search', '').strip()
        related_contact_id = request.query_params.get('related_contact')

        contacts = Contact.objects.for_user(request.user)
        if contact_search:
            contacts = contacts.filter(
                Q(first_name__icontains=contact_search)
                | Q(last_name__icontains=contact_search)
                | Q(preferred_name__icontains=contact_search)
            )
        contacts = contacts.order_by('first_name', 'last_name', 'id')[:limit]

        events = Event.objects.filter(user=request.user)
        if related_contact_id:
            try:
                related_contact_id = int(related_contact_id)
            except (TypeError, ValueError):
                raise ValidationError({
                    'related_contact': 'Enter a valid positive integer.'
                }) from None
            if related_contact_id <= 0:
                raise ValidationError({
                    'related_contact': 'Enter a valid positive integer.'
                })
            contact = get_object_or_404(
                Contact.objects.for_user(request.user),
                pk=related_contact_id,
            )
            events = events.filter(participants__contact=contact).distinct()
        if event_search:
            events = events.filter(title__icontains=event_search)
        events = events.order_by('-event_timestamp', '-id')[:limit]

        payload = {
            'contacts': [
                {'id': contact.id, 'display_name': str(contact)}
                for contact in contacts
            ],
            'events': [
                {'id': event.id, 'title': event.title}
                for event in events
            ],
        }
        return Response(self.get_serializer(payload).data)

    def _limit(self, request):
        try:
            limit = int(request.query_params.get('limit', 100))
        except (TypeError, ValueError):
            raise ValidationError({
                'limit': 'Enter a whole number from 1 through 100.'
            }) from None
        if limit < 1 or limit > 100:
            raise ValidationError({
                'limit': 'Enter a whole number from 1 through 100.'
            })
        return limit


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
