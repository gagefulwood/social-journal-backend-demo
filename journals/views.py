from django.utils.dateparse import parse_datetime
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.pagination import StandardResultsPagination
from core.permissions import IsOwner
from .filters import ExerciseFilter, LogFilter, ReflectionFilter
from .models import Exercise, Log, Reflection
from .serializers import (
    CombinedJournalItemSerializer,
    ExerciseListSerializer,
    ExerciseSerializer,
    LogListSerializer,
    LogSerializer,
    ReflectionListSerializer,
    ReflectionSerializer,
)


class JournalKindViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend]
    pagination_class = StandardResultsPagination
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset_model.objects.none()
        return self.queryset_model.objects.for_user(self.request.user).select_related(
            'event',
            'user',
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return self.list_serializer_class
        return self.detail_serializer_class

    def perform_create(self, serializer):
        event = self._validated_event(serializer)
        serializer.save(user=self.request.user, event=event)

    def perform_update(self, serializer):
        event = serializer.validated_data.get('event', serializer.instance.event)
        self._validate_event_owner(event)
        serializer.save()

    def _validated_event(self, serializer):
        event = serializer.validated_data.get('event')
        if event is None:
            raise ValidationError({'event': 'This field is required.'})
        self._validate_event_owner(event)
        return event

    def _validate_event_owner(self, event):
        if event.user_id != self.request.user.id:
            raise PermissionDenied(
                'You do not have permission to add a journal entry to this event.'
            )


class LogViewSet(JournalKindViewSet):
    queryset_model = Log
    detail_serializer_class = LogSerializer
    list_serializer_class = LogListSerializer
    filterset_class = LogFilter

    def get_queryset(self):
        return super().get_queryset().select_related('mood').prefetch_related('tags')


class ReflectionViewSet(JournalKindViewSet):
    queryset_model = Reflection
    detail_serializer_class = ReflectionSerializer
    list_serializer_class = ReflectionListSerializer
    filterset_class = ReflectionFilter


class ExerciseViewSet(JournalKindViewSet):
    queryset_model = Exercise
    detail_serializer_class = ExerciseSerializer
    list_serializer_class = ExerciseListSerializer
    filterset_class = ExerciseFilter

    def get_queryset(self):
        return super().get_queryset().prefetch_related('steps')


class JournalFeedView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination
    serializer_class = CombinedJournalItemSerializer
    http_method_names = ['get', 'head', 'options']

    def get(self, request, *args, **kwargs):
        items = self._combined_items(request)
        page = self.paginate_queryset(items)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    def _combined_items(self, request):
        kinds = self._requested_kinds(request)
        items = []
        if 'log' in kinds:
            items.extend(self._log_items(self._filtered_log_queryset(request)))
        if 'reflection' in kinds:
            items.extend(
                self._reflection_items(self._filtered_reflection_queryset(request))
            )
        if 'exercise' in kinds:
            items.extend(self._exercise_items(self._filtered_exercise_queryset(request)))
        return sorted(
            items,
            key=lambda item: item['created_timestamp'],
            reverse=True,
        )

    def _requested_kinds(self, request):
        requested = request.query_params.get('kind')
        allowed = {'log', 'reflection', 'exercise'}
        if not requested:
            return allowed
        kinds = {kind.strip() for kind in requested.split(',') if kind.strip()}
        invalid = kinds - allowed
        if invalid:
            raise ValidationError({'kind': 'Use log, reflection, or exercise.'})
        return kinds

    def _base_queryset(self, model, request):
        queryset = model.objects.for_user(request.user).select_related('event')
        event_id = request.query_params.get('event')
        created_after = request.query_params.get('created_after')
        created_before = request.query_params.get('created_before')
        title = request.query_params.get('title')
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        if created_after:
            queryset = queryset.filter(
                created_timestamp__gte=parse_datetime(created_after)
            )
        if created_before:
            queryset = queryset.filter(
                created_timestamp__lte=parse_datetime(created_before)
            )
        if title:
            queryset = queryset.filter(title__icontains=title)
        return queryset

    def _filtered_log_queryset(self, request):
        queryset = self._base_queryset(Log, request).select_related('mood')
        mood = request.query_params.get('mood')
        tags = request.query_params.get('tags')
        if mood:
            queryset = queryset.filter(mood_id=mood)
        if tags:
            queryset = queryset.filter(tags__id=tags)
        return queryset.prefetch_related('tags')

    def _filtered_reflection_queryset(self, request):
        queryset = self._base_queryset(Reflection, request)
        subtype = request.query_params.get('subtype')
        if subtype:
            queryset = queryset.filter(subtype=subtype)
        return queryset

    def _filtered_exercise_queryset(self, request):
        queryset = self._base_queryset(Exercise, request)
        subtype = request.query_params.get('subtype')
        if subtype:
            queryset = queryset.filter(subtype=subtype)
        return queryset

    def _log_items(self, queryset):
        return [
            {
                'id': log.id,
                'kind': 'log',
                'event': log.event_id,
                'label': log.title,
                'created_timestamp': log.created_timestamp,
                'updated_timestamp': log.updated_timestamp,
                'summary': {
                    'mood': log.mood_id,
                    'subtype': log.subtype,
                    'tag_count': log.tags.count(),
                },
            }
            for log in queryset
        ]

    def _reflection_items(self, queryset):
        return [
            {
                'id': reflection.id,
                'kind': 'reflection',
                'event': reflection.event_id,
                'label': reflection.title,
                'created_timestamp': reflection.created_timestamp,
                'updated_timestamp': reflection.updated_timestamp,
                'summary': {
                    'subtype': reflection.subtype,
                    'clarity_check': reflection.clarity_check,
                },
            }
            for reflection in queryset
        ]

    def _exercise_items(self, queryset):
        return [
            {
                'id': exercise.id,
                'kind': 'exercise',
                'event': exercise.event_id,
                'label': exercise.title,
                'created_timestamp': exercise.created_timestamp,
                'updated_timestamp': exercise.updated_timestamp,
                'summary': {
                    'subtype': exercise.subtype,
                    'measurement_delta': exercise.measurement_delta,
                },
            }
            for exercise in queryset
        ]
