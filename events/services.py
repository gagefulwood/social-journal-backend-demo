from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import F, Max, Q
from rest_framework.exceptions import ValidationError

from contacts.models import Contact
from media.models import MediaAsset

from .models import (
    Event,
    EventChapter,
    EventChapterParticipant,
    EventMedia,
    EventMediaCrop,
    EventParticipant,
)


UNSET = object()


def ready_event_media_queryset():
    '''Return renderable Event media without assuming a media migration landed.'''

    queryset = (
        EventMedia.objects.filter(media_asset__is_active=True)
        .select_related('media_asset', 'media_asset__media_type')
        .prefetch_related('crops')
        .order_by('display_order', 'id')
    )
    media_fields = {field.name for field in MediaAsset._meta.get_fields()}
    if 'status' in media_fields:
        queryset = queryset.filter(media_asset__status='ready')
    return queryset


def validate_event_end_against_chapters(event, end_timestamp):
    if end_timestamp is None:
        return
    affected = list(
        EventChapter.objects.filter(event=event)
        .filter(
            Q(start_timestamp__gt=end_timestamp)
            | Q(end_timestamp__gt=end_timestamp)
        )
        .order_by('position', 'id')
        .values_list('id', flat=True)
    )
    if affected:
        raise ValidationError({
            'end_timestamp': {
                'message': 'Event end cannot exclude an existing chapter.',
                'chapter_ids': [str(chapter_id) for chapter_id in affected],
            }
        })


@transaction.atomic
def replace_event_participants(*, user, event, contacts):
    event = _lock_event(user=user, event=event)
    contacts = _unique_contacts(contacts)
    _validate_owned_contacts(user=user, contacts=contacts)

    existing = {
        participant.contact_id: participant
        for participant in EventParticipant.objects.select_for_update().filter(
            event=event,
        )
    }
    requested_ids = {contact.id for contact in contacts}
    removed_ids = set(existing) - requested_ids
    blocked_links = list(
        EventChapterParticipant.objects.filter(
            chapter__event=event,
            chapter__inherits_event_participants=False,
            contact_id__in=removed_ids,
        )
        .order_by('chapter__position', 'chapter_id')
        .values_list('chapter_id', 'contact_id')
    )
    if blocked_links:
        raise ValidationError({
            'participants': {
                'message': (
                    'A participant used explicitly by a chapter cannot be '
                    'removed from the Event.'
                ),
                'chapter_ids': list(dict.fromkeys(
                    str(chapter_id) for chapter_id, _ in blocked_links
                )),
            }
        })

    for contact in contacts:
        if contact.id not in existing:
            EventParticipant.objects.create(event=event, contact=contact)
    for contact_id in removed_ids:
        existing[contact_id].delete()

    prefetched = getattr(event, '_prefetched_objects_cache', None)
    if prefetched is not None:
        prefetched.pop('participants', None)
    return event


def validate_event_participant_replacement(*, event, requested_contacts):
    requested_ids = {contact.id for contact in requested_contacts}
    current_ids = set(
        EventParticipant.objects.select_for_update()
        .filter(event=event)
        .values_list('contact_id', flat=True)
    )
    blocked_links = list(
        EventChapterParticipant.objects.select_for_update()
        .filter(
            chapter__event=event,
            chapter__inherits_event_participants=False,
            contact_id__in=current_ids - requested_ids,
        )
        .order_by('chapter__position', 'chapter_id')
        .values_list('chapter_id', flat=True)
    )
    if blocked_links:
        raise ValidationError({
            'participants': {
                'message': (
                    'A participant used explicitly by a chapter cannot be '
                    'removed from the Event.'
                ),
                'chapter_ids': list(dict.fromkeys(
                    str(chapter_id) for chapter_id in blocked_links
                )),
            }
        })


@transaction.atomic
def materialize_legacy_chapter(*, user, event, values=None):
    """Materialize and optionally edit the projection as one transaction.

    The optional write payload lets the projected-chapter editor avoid a
    materialize-then-PATCH sequence that could otherwise leave a chapter row
    behind when the second request fails. Replaying the same request remains
    idempotent: an existing first chapter is locked and receives the same
    validated values.
    """

    event = _lock_event(user=user, event=event)
    chapter, created = _materialize_legacy_chapter_locked(event)
    if values is None:
        return chapter, created

    values = dict(values)
    participants = values.pop('participant_contacts', UNSET)
    normalized = _validated_chapter_values(
        event=event,
        values=values,
        chapter=chapter,
    )
    for field, value in normalized.items():
        setattr(chapter, field, value)
    if normalized:
        chapter.save()
    _replace_chapter_participants(
        user=user,
        chapter=chapter,
        contacts=([] if participants is UNSET else participants),
        contacts_were_supplied=participants is not UNSET,
    )
    return chapter, created


@transaction.atomic
def create_event_chapter(*, user, event, values):
    event = _lock_event(user=user, event=event)
    chapters = list(
        EventChapter.objects.select_for_update()
        .filter(event=event)
        .order_by('position', 'id')
    )
    if not chapters:
        _materialize_legacy_chapter_locked(event)

    values = dict(values)
    participants = values.pop('participant_contacts', UNSET)
    normalized = _validated_chapter_values(event=event, values=values)
    last_position = (
        EventChapter.objects.filter(event=event)
        .aggregate(last=Max('position'))['last']
    )
    chapter = EventChapter.objects.create(
        event=event,
        position=0 if last_position is None else last_position + 1,
        **normalized,
    )
    _replace_chapter_participants(
        user=user,
        chapter=chapter,
        contacts=([] if participants is UNSET else participants),
        contacts_were_supplied=participants is not UNSET,
    )
    return chapter


@transaction.atomic
def update_event_chapter(*, user, event, chapter, values):
    event = _lock_event(user=user, event=event)
    chapter = _lock_chapter(event=event, chapter=chapter)
    values = dict(values)
    participants = values.pop('participant_contacts', UNSET)
    normalized = _validated_chapter_values(
        event=event,
        values=values,
        chapter=chapter,
    )
    for field, value in normalized.items():
        setattr(chapter, field, value)
    if normalized:
        chapter.save()
    _replace_chapter_participants(
        user=user,
        chapter=chapter,
        contacts=([] if participants is UNSET else participants),
        contacts_were_supplied=participants is not UNSET,
    )
    return chapter


@transaction.atomic
def reorder_event_chapters(*, user, event, chapter_ids):
    event = _lock_event(user=user, event=event)
    chapters = list(
        EventChapter.objects.select_for_update()
        .filter(event=event)
        .order_by('position', 'id')
    )
    chapter_ids = list(chapter_ids)
    if len(chapter_ids) != len(set(chapter_ids)):
        raise ValidationError({'chapter_ids': 'Chapter IDs cannot repeat.'})
    existing_by_id = {chapter.id: chapter for chapter in chapters}
    if set(chapter_ids) != set(existing_by_id):
        raise ValidationError({
            'chapter_ids': (
                'Provide every chapter in this Event exactly once.'
            )
        })
    if not chapters:
        return []

    offset = max(chapter.position for chapter in chapters) + len(chapters) + 1
    EventChapter.objects.filter(event=event).update(position=F('position') + offset)
    ordered = []
    for position, chapter_id in enumerate(chapter_ids):
        chapter = existing_by_id[chapter_id]
        chapter.position = position
        ordered.append(chapter)
    EventChapter.objects.bulk_update(ordered, ['position'])
    return ordered


@transaction.atomic
def delete_event_chapter(*, user, event, chapter):
    event = _lock_event(user=user, event=event)
    chapter = _lock_chapter(event=event, chapter=chapter)
    _promote_chapter_media(event=event, chapter=chapter)
    chapter.delete()
    _compact_chapter_positions(event)


@transaction.atomic
def create_event_media(*, user, event, values):
    event = _lock_event(user=user, event=event)
    values = dict(values)
    chapter = values.pop('chapter', None)
    if chapter is not None:
        chapter = _lock_chapter(event=event, chapter=chapter)
    asset = _lock_ready_asset(user=user, asset=values.pop('media_asset'))
    crops = values.pop('crops', [])

    _validate_event_media_limits(event=event, chapter=chapter, asset=asset)
    _validate_event_media_values(asset=asset, values=values)
    scope = _event_media_scope(event=event, chapter=chapter)
    if scope.filter(media_asset=asset).exists():
        raise ValidationError({
            'media_asset_id': 'This media asset is already attached in this scope.'
        })
    last_position = scope.aggregate(last=Max('display_order'))['last']
    if values.get('is_cover'):
        scope.update(is_cover=False)
    attachment = EventMedia.objects.create(
        event=event,
        chapter=chapter,
        media_asset=asset,
        display_order=0 if last_position is None else last_position + 1,
        **values,
    )
    _replace_event_media_crops(attachment=attachment, crops=crops)
    return attachment


@transaction.atomic
def update_event_media(*, user, event, attachment, values):
    event = _lock_event(user=user, event=event)
    attachment = (
        EventMedia.objects.select_for_update(of=('self',))
        .select_related('chapter', 'media_asset')
        .get(pk=attachment.pk, event=event)
    )
    values = dict(values)
    crops = values.pop('crops', UNSET)
    if 'chapter' in values:
        requested_chapter = values.pop('chapter')
        requested_chapter_id = (
            requested_chapter.pk if requested_chapter is not None else None
        )
        if requested_chapter_id != attachment.chapter_id:
            raise ValidationError({
                'chapter_id': (
                    'Move media by removing and attaching it in the new scope.'
                )
            })
    if 'media_asset' in values:
        values.pop('media_asset')
        raise ValidationError({
            'media_asset_id': 'The attached media asset cannot be changed.'
        })

    proposed = {
        'alt_text': values.get('alt_text', attachment.alt_text),
        'decorative': values.get('decorative', attachment.decorative),
        'is_cover': values.get('is_cover', attachment.is_cover),
    }
    for focal_field in ('focal_x', 'focal_y'):
        if focal_field in values:
            proposed[focal_field] = values[focal_field]
    _validate_event_media_values(
        asset=attachment.media_asset,
        values=proposed,
    )
    scope = _event_media_scope(event=event, chapter=attachment.chapter)
    if values.get('is_cover'):
        scope.exclude(pk=attachment.pk).update(is_cover=False)
    for field, value in values.items():
        setattr(attachment, field, value)
    if values:
        attachment.save()
    if crops is not UNSET:
        _replace_event_media_crops(attachment=attachment, crops=crops)
    return attachment


@transaction.atomic
def delete_event_media(*, user, event, attachment):
    event = _lock_event(user=user, event=event)
    attachment = (
        EventMedia.objects.select_for_update(of=('self',))
        .select_related('chapter')
        .get(pk=attachment.pk, event=event)
    )
    chapter = attachment.chapter
    attachment.delete()
    _compact_event_media_positions(event=event, chapter=chapter)


@transaction.atomic
def reorder_event_media(*, user, event, chapter, attachment_ids):
    event = _lock_event(user=user, event=event)
    if chapter is not None:
        chapter = _lock_chapter(event=event, chapter=chapter)
    attachments = list(
        _event_media_scope(event=event, chapter=chapter)
        .select_for_update()
        .order_by('display_order', 'id')
    )
    attachment_ids = list(attachment_ids)
    if len(attachment_ids) != len(set(attachment_ids)):
        raise ValidationError({'media_ids': 'Media IDs cannot repeat.'})
    existing_by_id = {attachment.id: attachment for attachment in attachments}
    if set(attachment_ids) != set(existing_by_id):
        raise ValidationError({
            'media_ids': 'Provide every media attachment in this scope exactly once.'
        })
    if not attachments:
        return []

    offset = (
        max(attachment.display_order for attachment in attachments)
        + len(attachments)
        + 1
    )
    scope = _event_media_scope(event=event, chapter=chapter)
    scope.update(display_order=F('display_order') + offset)
    ordered = []
    for display_order, attachment_id in enumerate(attachment_ids):
        attachment = existing_by_id[attachment_id]
        attachment.display_order = display_order
        ordered.append(attachment)
    EventMedia.objects.bulk_update(ordered, ['display_order'])
    return ordered


def _lock_event(*, user, event):
    try:
        return Event.objects.select_for_update().get(pk=event.pk, user=user)
    except Event.DoesNotExist:
        raise ValidationError({'event': 'Event is no longer available.'})


def _lock_chapter(*, event, chapter):
    try:
        return EventChapter.objects.select_for_update().get(
            pk=chapter.pk,
            event=event,
        )
    except EventChapter.DoesNotExist:
        raise ValidationError({'chapter_id': 'Chapter is not part of this Event.'})


def _materialize_legacy_chapter_locked(event):
    existing = (
        EventChapter.objects.select_for_update()
        .filter(event=event)
        .order_by('position', 'id')
        .first()
    )
    if existing is not None:
        return existing, False
    title = event.title.strip()[:120] or 'Moment'
    chapter = EventChapter.objects.create(
        event=event,
        title=title,
        position=0,
        start_timestamp=event.event_timestamp,
        end_timestamp=event.end_timestamp,
        location_label=event.location_label,
        note=event.description,
        inherits_event_participants=True,
    )
    return chapter, True


def _validated_chapter_values(*, event, values, chapter=None):
    values = dict(values)
    if 'title' in values:
        values['title'] = values['title'].strip()
        if not values['title']:
            raise ValidationError({'title': 'Enter a chapter title.'})

    start = values.get(
        'start_timestamp',
        chapter.start_timestamp if chapter is not None else None,
    )
    end = values.get(
        'end_timestamp',
        chapter.end_timestamp if chapter is not None else None,
    )
    errors = {}
    if start is not None and start < event.event_timestamp:
        errors['start_timestamp'] = (
            'Chapter start cannot be before the Event start.'
        )
    if end is not None and end < event.event_timestamp:
        errors['end_timestamp'] = (
            'Chapter end cannot be before the Event start.'
        )
    if start is not None and end is not None and end < start:
        errors['end_timestamp'] = (
            'Chapter end must be on or after the chapter start.'
        )
    if event.end_timestamp is not None:
        if start is not None and start > event.end_timestamp:
            errors['start_timestamp'] = (
                'Chapter start cannot be after the Event end.'
            )
        if end is not None and end > event.end_timestamp:
            errors['end_timestamp'] = (
                'Chapter end cannot be after the Event end.'
            )
    if errors:
        raise ValidationError(errors)
    return values


def _replace_chapter_participants(
    *,
    user,
    chapter,
    contacts,
    contacts_were_supplied,
):
    inherits = chapter.inherits_event_participants
    if not contacts_were_supplied:
        if inherits:
            EventChapterParticipant.objects.filter(chapter=chapter).delete()
        return

    contacts = _unique_contacts(contacts)
    _validate_owned_contacts(user=user, contacts=contacts)
    if inherits and contacts:
        raise ValidationError({
            'participant_ids': (
                'Inherited chapters cannot also store explicit participants.'
            )
        })
    if inherits:
        EventChapterParticipant.objects.filter(chapter=chapter).delete()
        return

    parent_ids = set(
        EventParticipant.objects.filter(event=chapter.event)
        .values_list('contact_id', flat=True)
    )
    invalid = [contact.id for contact in contacts if contact.id not in parent_ids]
    if invalid:
        raise ValidationError({
            'participant_ids': (
                'Chapter participants must already participate in the Event.'
            )
        })
    EventChapterParticipant.objects.filter(chapter=chapter).delete()
    EventChapterParticipant.objects.bulk_create(
        EventChapterParticipant(
            chapter=chapter,
            contact=contact,
            display_order=index,
        )
        for index, contact in enumerate(contacts)
    )


def _validate_owned_contacts(*, user, contacts):
    if any(contact.user_id != user.id or not contact.is_active for contact in contacts):
        raise ValidationError({
            'participant_ids': 'Select active contacts owned by this user.'
        })


def _unique_contacts(contacts):
    unique = []
    seen = set()
    for contact in contacts:
        if contact.id not in seen:
            seen.add(contact.id)
            unique.append(contact)
    return unique


def _lock_ready_asset(*, user, asset):
    try:
        asset = MediaAsset.objects.select_for_update().get(
            pk=asset.pk,
            user=user,
            is_active=True,
        )
    except MediaAsset.DoesNotExist:
        raise ValidationError({
            'media_asset_id': 'Select media owned by the requesting user.'
        })
    status = getattr(asset, 'status', 'ready')
    if status != 'ready':
        raise ValidationError({
            'media_asset_id': 'Media must finish processing before attachment.'
        })
    return asset


def _validate_event_media_limits(*, event, chapter, asset):
    event_limit = getattr(settings, 'MEDIA_EVENT_MAX_ASSETS', 40)
    chapter_limit = getattr(settings, 'MEDIA_CHAPTER_MAX_ASSETS', 12)
    if EventMedia.objects.filter(event=event).count() >= event_limit:
        raise ValidationError({
            'media_asset_id': f'An Event can contain at most {event_limit} assets.'
        })
    if (
        chapter is not None
        and EventMedia.objects.filter(chapter=chapter).count() >= chapter_limit
    ):
        raise ValidationError({
            'media_asset_id': (
                f'A chapter can contain at most {chapter_limit} assets.'
            )
        })

    event_byte_limit = getattr(
        settings,
        'MEDIA_EVENT_ORIGINAL_BYTES_MAX',
        2 * 1024 * 1024 * 1024,
    )
    chapter_byte_limit = getattr(
        settings,
        'MEDIA_CHAPTER_ORIGINAL_BYTES_MAX',
        750 * 1024 * 1024,
    )
    event_asset_sizes = dict(
        EventMedia.objects.filter(event=event)
        .values_list('media_asset_id', 'media_asset__file_size')
        .distinct()
    )
    event_bytes = sum(event_asset_sizes.values())
    if asset.id not in event_asset_sizes:
        event_bytes += asset.file_size
    if event_bytes > event_byte_limit:
        raise ValidationError({
            'media_asset_id': (
                f'Event originals cannot exceed {event_byte_limit} bytes.'
            )
        })
    if chapter is not None:
        chapter_asset_sizes = dict(
            EventMedia.objects.filter(chapter=chapter)
            .values_list('media_asset_id', 'media_asset__file_size')
            .distinct()
        )
        chapter_bytes = sum(chapter_asset_sizes.values())
        if asset.id not in chapter_asset_sizes:
            chapter_bytes += asset.file_size
        if chapter_bytes > chapter_byte_limit:
            raise ValidationError({
                'media_asset_id': (
                    'Chapter originals cannot exceed '
                    f'{chapter_byte_limit} bytes.'
                )
            })


def _validate_event_media_values(*, asset, values):
    content_type = (
        getattr(asset, 'detected_content_type', '')
        or getattr(asset, 'detected_mime_type', '')
        or asset.content_type
    ).lower()
    if not content_type.startswith(('image/', 'video/', 'audio/')):
        raise ValidationError({
            'media_asset_id': 'Only supported image, video, or audio media can attach.'
        })
    is_image = content_type.startswith('image/')
    if values.get('is_cover') and not is_image:
        raise ValidationError({
            'is_cover': 'Only a ready image can be used as a cover.'
        })
    if (
        is_image
        and not values.get('decorative', False)
        and not str(values.get('alt_text', '')).strip()
    ):
        raise ValidationError({
            'alt_text': 'Describe this image or mark it decorative.'
        })
    if not is_image and any(field in values for field in ('focal_x', 'focal_y')):
        raise ValidationError({
            'focal_x': 'Focal points require an image attachment.'
        })
    for field in ('focal_x', 'focal_y'):
        if field not in values:
            continue
        value = _decimal(values[field], field)
        if value < 0 or value > 1:
            raise ValidationError({field: 'Use a normalized value from 0 to 1.'})


def _replace_event_media_crops(*, attachment, crops):
    content_type = (
        getattr(attachment.media_asset, 'detected_content_type', '')
        or getattr(attachment.media_asset, 'detected_mime_type', '')
        or attachment.media_asset.content_type
    ).lower()
    if crops and not content_type.startswith('image/'):
        raise ValidationError({'crops': 'Crops require an image attachment.'})
    validated = {}
    for crop in crops:
        crop = dict(crop)
        kind = crop.get('crop_kind')
        if kind in validated:
            raise ValidationError({'crops': 'Each crop kind can appear only once.'})
        expected_kind = (
            EventMediaCrop.KIND_EVENT_COVER
            if attachment.chapter_id is None
            else EventMediaCrop.KIND_CHAPTER_CAROUSEL
        )
        if kind != expected_kind:
            raise ValidationError({
                'crops': f'Use {expected_kind} for this media scope.'
            })
        _validate_crop(crop)
        validated[kind] = crop
    EventMediaCrop.objects.filter(event_media=attachment).exclude(
        crop_kind__in=validated,
    ).delete()
    for kind, crop in validated.items():
        defaults = dict(crop)
        defaults.pop('crop_kind')
        EventMediaCrop.objects.update_or_create(
            event_media=attachment,
            crop_kind=kind,
            defaults=defaults,
        )


def _validate_crop(crop):
    kind = crop.get('crop_kind')
    if kind not in dict(EventMediaCrop.KIND_CHOICES):
        raise ValidationError({'crops': 'Select a supported crop kind.'})
    try:
        x = _decimal(crop['x'], 'x')
        y = _decimal(crop['y'], 'y')
        width = _decimal(crop['width'], 'width')
        height = _decimal(crop['height'], 'height')
    except KeyError as exc:
        raise ValidationError({
            'crops': f'Crop requires {exc.args[0]}.'
        }) from None
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValidationError({'crops': 'Crop values must be normalized and positive.'})
    if x + width > 1 or y + height > 1:
        raise ValidationError({'crops': 'Crop rectangle must remain within the source.'})


def _decimal(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: 'Enter a decimal value.'}) from None


def _event_media_scope(*, event, chapter):
    if chapter is None:
        return EventMedia.objects.filter(event=event, chapter__isnull=True)
    return EventMedia.objects.filter(event=event, chapter=chapter)


def _promote_chapter_media(*, event, chapter):
    chapter_media = list(
        EventMedia.objects.select_for_update()
        .filter(event=event, chapter=chapter)
        .select_related('media_asset')
        .order_by('display_order', 'id')
    )
    if not chapter_media:
        return
    whole_media = list(
        EventMedia.objects.select_for_update()
        .filter(event=event, chapter__isnull=True)
        .order_by('display_order', 'id')
    )
    whole_by_asset = {
        attachment.media_asset_id: attachment for attachment in whole_media
    }
    has_cover = any(attachment.is_cover for attachment in whole_media)
    next_position = (
        max((attachment.display_order for attachment in whole_media), default=-1)
        + 1
    )
    for attachment in chapter_media:
        attachment.crops.all().delete()
        existing = whole_by_asset.get(attachment.media_asset_id)
        content_type = (
            getattr(attachment.media_asset, 'detected_content_type', '')
            or getattr(attachment.media_asset, 'detected_mime_type', '')
            or attachment.media_asset.content_type
        ).lower()
        promote_cover = (
            attachment.is_cover
            and content_type.startswith('image/')
            and not has_cover
        )
        if existing is not None:
            if promote_cover:
                existing.is_cover = True
                existing.save(update_fields=['is_cover', 'updated_timestamp'])
                has_cover = True
            attachment.delete()
            continue
        attachment.chapter = None
        attachment.display_order = next_position
        attachment.is_cover = promote_cover
        attachment.save(
            update_fields=[
                'chapter',
                'display_order',
                'is_cover',
                'updated_timestamp',
            ]
        )
        whole_by_asset[attachment.media_asset_id] = attachment
        next_position += 1
        has_cover = has_cover or promote_cover


def _compact_chapter_positions(event):
    chapters = list(
        EventChapter.objects.select_for_update()
        .filter(event=event)
        .order_by('position', 'id')
    )
    if not chapters:
        return
    offset = max(chapter.position for chapter in chapters) + len(chapters) + 1
    EventChapter.objects.filter(event=event).update(position=F('position') + offset)
    for position, chapter in enumerate(chapters):
        chapter.position = position
    EventChapter.objects.bulk_update(chapters, ['position'])


def _compact_event_media_positions(*, event, chapter):
    attachments = list(
        _event_media_scope(event=event, chapter=chapter)
        .select_for_update()
        .order_by('display_order', 'id')
    )
    if not attachments:
        return
    offset = (
        max(attachment.display_order for attachment in attachments)
        + len(attachments)
        + 1
    )
    scope = _event_media_scope(event=event, chapter=chapter)
    scope.update(display_order=F('display_order') + offset)
    for display_order, attachment in enumerate(attachments):
        attachment.display_order = display_order
    EventMedia.objects.bulk_update(attachments, ['display_order'])
