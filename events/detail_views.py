import uuid

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Event,
    EventChapter,
    EventChapterParticipant,
    EventMedia,
    EventParticipant,
)
from .serializers import (
    EventChapterDetailSerializer,
    EventChapterHeaderSerializer,
    EventChapterReorderSerializer,
    EventChapterWriteSerializer,
    EventMediaAttachmentSerializer,
    EventMediaReorderSerializer,
    EventMediaWriteSerializer,
)
from .services import (
    create_event_chapter,
    create_event_media,
    delete_event_chapter,
    delete_event_media,
    materialize_legacy_chapter,
    ready_event_media_queryset,
    reorder_event_chapters,
    reorder_event_media,
    update_event_chapter,
    update_event_media,
)


def _participant_queryset(user):
    return (
        EventParticipant.objects.filter(
            contact__is_active=True,
            contact__user=user,
        )
        .select_related(
            'contact',
            'contact__relation',
            'contact__occupation',
            'contact__profile_picture',
            'contact__profile_picture__media_type',
        )
        .order_by('id')
    )


def _event_for_request(request, event_id):
    return get_object_or_404(
        Event.objects.filter(user=request.user)
        .select_related('user', 'context_category', 'interaction_mode', 'mood')
        .prefetch_related(
            Prefetch(
                'participants',
                queryset=_participant_queryset(request.user),
            )
        ),
        pk=event_id,
    )


def _chapter_queryset(event, user):
    explicit_participants = (
        EventChapterParticipant.objects.filter(
            contact__is_active=True,
            contact__user=user,
        )
        .select_related(
            'contact',
            'contact__relation',
            'contact__occupation',
            'contact__profile_picture',
            'contact__profile_picture__media_type',
        )
        .order_by('display_order', 'id')
    )
    return (
        EventChapter.objects.filter(event=event)
        .select_related('event', 'event__user')
        .prefetch_related(
            Prefetch('participant_links', queryset=explicit_participants),
            Prefetch(
                'media_attachments',
                queryset=ready_event_media_queryset(),
                to_attr='ready_media',
            ),
        )
        .order_by('position', 'id')
    )


class EventChapterCollectionView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request, event_id):
        event = _event_for_request(request, event_id)
        chapters = list(_chapter_queryset(event, request.user))
        serializer = EventChapterHeaderSerializer(
            chapters,
            many=True,
            context={'request': request, 'event': event},
        )
        return Response(serializer.data)

    def post(self, request, event_id):
        event = _event_for_request(request, event_id)
        serializer = EventChapterWriteSerializer(
            data=request.data,
            context={'request': request, 'event': event},
        )
        serializer.is_valid(raise_exception=True)
        chapter = create_event_chapter(
            user=request.user,
            event=event,
            values=serializer.validated_data,
        )
        chapter = _chapter_queryset(event, request.user).get(pk=chapter.pk)
        return Response(
            EventChapterDetailSerializer(
                chapter,
                context={'request': request, 'event': event},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class EventChapterDetailView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get(self, request, event_id, chapter_id):
        event = _event_for_request(request, event_id)
        chapter = get_object_or_404(
            _chapter_queryset(event, request.user),
            pk=chapter_id,
        )
        return Response(
            EventChapterDetailSerializer(
                chapter,
                context={'request': request, 'event': event},
            ).data
        )

    def patch(self, request, event_id, chapter_id):
        event = _event_for_request(request, event_id)
        chapter = get_object_or_404(
            EventChapter.objects.filter(event=event),
            pk=chapter_id,
        )
        serializer = EventChapterWriteSerializer(
            data=request.data,
            partial=True,
            context={'request': request, 'event': event},
        )
        serializer.is_valid(raise_exception=True)
        chapter = update_event_chapter(
            user=request.user,
            event=event,
            chapter=chapter,
            values=serializer.validated_data,
        )
        chapter = _chapter_queryset(event, request.user).get(pk=chapter.pk)
        return Response(
            EventChapterDetailSerializer(
                chapter,
                context={'request': request, 'event': event},
            ).data
        )

    def delete(self, request, event_id, chapter_id):
        event = _event_for_request(request, event_id)
        chapter = get_object_or_404(
            EventChapter.objects.filter(event=event),
            pk=chapter_id,
        )
        delete_event_chapter(
            user=request.user,
            event=event,
            chapter=chapter,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventChapterReorderView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['put', 'head', 'options']

    def put(self, request, event_id):
        event = _event_for_request(request, event_id)
        serializer = EventChapterReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reorder_event_chapters(
            user=request.user,
            event=event,
            chapter_ids=serializer.validated_data['chapter_ids'],
        )
        chapters = list(_chapter_queryset(event, request.user))
        return Response(
            EventChapterHeaderSerializer(
                chapters,
                many=True,
                context={'request': request, 'event': event},
            ).data
        )


class EventChapterMaterializeLegacyView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['post', 'head', 'options']

    def post(self, request, event_id):
        event = _event_for_request(request, event_id)
        serializer = EventChapterWriteSerializer(
            data=request.data,
            partial=True,
            context={'request': request, 'event': event},
        )
        serializer.is_valid(raise_exception=True)
        chapter, created = materialize_legacy_chapter(
            user=request.user,
            event=event,
            values=serializer.validated_data,
        )
        chapter = _chapter_queryset(event, request.user).get(pk=chapter.pk)
        return Response(
            EventChapterDetailSerializer(
                chapter,
                context={'request': request, 'event': event},
            ).data,
            status=(status.HTTP_201_CREATED if created else status.HTTP_200_OK),
        )


class EventMediaCollectionView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request, event_id):
        event = _event_for_request(request, event_id)
        queryset = ready_event_media_queryset().filter(event=event)
        chapter_value = request.query_params.get('chapter_id')
        if chapter_value == 'event':
            queryset = queryset.filter(chapter__isnull=True)
        elif chapter_value:
            try:
                chapter_id = uuid.UUID(chapter_value)
            except (TypeError, ValueError, AttributeError):
                raise ValidationError({
                    'chapter_id': 'Enter a valid chapter ID or use "event".'
                }) from None
            chapter = get_object_or_404(
                EventChapter.objects.filter(event=event),
                pk=chapter_id,
            )
            queryset = queryset.filter(chapter=chapter)
        else:
            queryset = queryset.order_by(
                'chapter__position',
                'display_order',
                'id',
            )
        return Response(
            EventMediaAttachmentSerializer(
                queryset,
                many=True,
                context={'request': request},
            ).data
        )

    def post(self, request, event_id):
        event = _event_for_request(request, event_id)
        serializer = EventMediaWriteSerializer(
            data=request.data,
            context={'request': request, 'event': event},
        )
        serializer.is_valid(raise_exception=True)
        attachment = create_event_media(
            user=request.user,
            event=event,
            values=serializer.validated_data,
        )
        attachment = ready_event_media_queryset().get(pk=attachment.pk)
        return Response(
            EventMediaAttachmentSerializer(
                attachment,
                context={'request': request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class EventMediaDetailView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get(self, request, event_id, attachment_id):
        event = _event_for_request(request, event_id)
        attachment = get_object_or_404(
            ready_event_media_queryset().filter(event=event),
            pk=attachment_id,
        )
        return Response(
            EventMediaAttachmentSerializer(
                attachment,
                context={'request': request},
            ).data
        )

    def patch(self, request, event_id, attachment_id):
        event = _event_for_request(request, event_id)
        attachment = get_object_or_404(
            ready_event_media_queryset().filter(event=event),
            pk=attachment_id,
        )
        serializer = EventMediaWriteSerializer(
            data=request.data,
            partial=True,
            context={'request': request, 'event': event},
        )
        serializer.is_valid(raise_exception=True)
        attachment = update_event_media(
            user=request.user,
            event=event,
            attachment=attachment,
            values=serializer.validated_data,
        )
        attachment = ready_event_media_queryset().get(pk=attachment.pk)
        return Response(
            EventMediaAttachmentSerializer(
                attachment,
                context={'request': request},
            ).data
        )

    def delete(self, request, event_id, attachment_id):
        event = _event_for_request(request, event_id)
        attachment = get_object_or_404(
            EventMedia.objects.filter(event=event),
            pk=attachment_id,
        )
        delete_event_media(
            user=request.user,
            event=event,
            attachment=attachment,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventMediaReorderView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['put', 'head', 'options']

    def put(self, request, event_id):
        event = _event_for_request(request, event_id)
        serializer = EventMediaReorderSerializer(
            data=request.data,
            context={'request': request, 'event': event},
        )
        serializer.is_valid(raise_exception=True)
        ordered = reorder_event_media(
            user=request.user,
            event=event,
            chapter=serializer.validated_data.get('chapter'),
            attachment_ids=serializer.validated_data['media_ids'],
        )
        ordered_ids = [attachment.id for attachment in ordered]
        attachments = {
            attachment.id: attachment
            for attachment in ready_event_media_queryset().filter(
                pk__in=ordered_ids,
            )
        }
        return Response(
            EventMediaAttachmentSerializer(
                [attachments[attachment_id] for attachment_id in ordered_ids],
                many=True,
                context={'request': request},
            ).data
        )
