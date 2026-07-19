from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from contacts.models import (
    Fact,
    Observation,
    OBSERVATION_STATUS_CHOICES,
    OBSERVATION_TYPE_CHOICES,
)

from .models import (
    EmotionalReflectionDetail,
    Log,
    Reflection,
)


JOURNAL_STEPS = {
    Log.FORMAT_LEGACY: ['legacy'],
    Log.FORMAT_EPISODE: ['episode'],
    Log.FORMAT_SOCIAL_ENERGY: ['social_energy'],
    Log.FORMAT_SENTIMENT: ['sentiment'],
    Reflection.FORMAT_LEGACY: ['legacy'],
    Reflection.FORMAT_INTERACTION: [
        'focus',
        'exchange',
        'meaning',
        'carry_forward',
        'review',
    ],
    Reflection.FORMAT_MOMENT: [
        'focus',
        'notice',
        'meaning',
        'carry_forward',
        'review',
    ],
    Reflection.FORMAT_EMOTIONAL: [
        'focus',
        'feelings',
        'understand',
        'carry_forward',
        'review',
    ],
    Reflection.FORMAT_FREE: ['writing', 'carry_forward', 'review'],
}
LOG_FORMAT_BREAKDOWN_UNSPECIFIED = 'unspecified'
SPECIFIC_LOG_FORMATS = (
    Log.FORMAT_EPISODE,
    Log.FORMAT_SOCIAL_ENERGY,
    Log.FORMAT_SENTIMENT,
)


def normalize_log_format_breakdown_key(value):
    if value in SPECIFIC_LOG_FORMATS:
        return value
    return LOG_FORMAT_BREAKDOWN_UNSPECIFIED


def progress_for(journal):
    steps = JOURNAL_STEPS.get(journal.format, ['writing'])
    total = len(steps)
    if journal.status == journal.STATUS_COMPLETED:
        completed = total
    elif journal.current_step in steps:
        completed = steps.index(journal.current_step)
    else:
        completed = 0
    return {
        'current_step': journal.current_step,
        'completed_steps': completed,
        'total_steps': total,
        'percent': round((completed / total) * 100) if total else 0,
    }


def completion_errors(journal):
    errors = {}
    if isinstance(journal, Log):
        _validate_log_completion(journal, errors)
    else:
        _validate_reflection_completion(journal, errors)
    return errors


def _require(errors, field, value, message='This field is required to complete.'):
    if value is None or value == '' or value == [] or value == 0:
        errors[field] = message


def _validate_log_completion(log, errors):
    if log.format == Log.FORMAT_LEGACY:
        return
    _require(errors, 'occurred_at', log.occurred_at)
    if log.format == Log.FORMAT_EPISODE:
        _require(errors, 'title', log.title)
        detail = getattr(log, 'episode_detail', None)
        _require(errors, 'detail.category_id', getattr(detail, 'category_id', None))
        if detail and not detail.is_ongoing:
            _require(errors, 'detail.ended_at', detail.ended_at)
            if detail.ended_at and log.occurred_at and detail.ended_at < log.occurred_at:
                errors['detail.ended_at'] = 'End time must be on or after start time.'
    elif log.format == Log.FORMAT_SOCIAL_ENERGY:
        detail = getattr(log, 'social_energy_detail', None)
        for field in (
            'battery_effect',
            'mood_shift',
            'behavioral_effect',
            'interaction_context',
            'group_size',
            'familiarity',
            'setting',
        ):
            _require(errors, f'detail.{field}', getattr(detail, field, None))
    elif log.format == Log.FORMAT_SENTIMENT:
        _require(errors, 'primary_contact_id', log.primary_contact_id)
        detail = getattr(log, 'sentiment_detail', None)
        for field in (
            'before_state_id',
            'after_state_id',
        ):
            _require(errors, f'detail.{field}', getattr(detail, field, None))


def _validate_reflection_completion(reflection, errors):
    if reflection.format == Reflection.FORMAT_LEGACY:
        return
    if reflection.format == Reflection.FORMAT_INTERACTION:
        _require(errors, 'primary_contact_id', reflection.primary_contact_id)
        _require(errors, 'occurred_at', reflection.occurred_at)
        detail = getattr(reflection, 'interaction_detail', None)
        for field in (
            'topic_or_activity',
            'user_actions',
            'contact_actions',
            'contact_response',
            'user_response',
            'feelings_now',
            'important_to_understand',
        ):
            _require(errors, f'detail.{field}', getattr(detail, field, None))
    elif reflection.format == Reflection.FORMAT_MOMENT:
        detail = getattr(reflection, 'moment_detail', None)
        for field in (
            'focus_moment',
            'what_happened',
            'noticed_around',
            'response',
            'stood_out',
            'meaning_now',
            'remember',
        ):
            _require(errors, f'detail.{field}', getattr(detail, field, None))
    elif reflection.format == Reflection.FORMAT_EMOTIONAL:
        detail = getattr(reflection, 'emotional_detail', None)
        emotion_count = detail.emotions.count() if detail else 0
        manifestation_count = detail.manifestations.count() if detail else 0
        _require(errors, 'detail.emotion_ids', emotion_count)
        _require(errors, 'detail.situation', getattr(detail, 'situation', None))
        _require(errors, 'detail.manifestations', manifestation_count)
        _require(
            errors,
            'detail.connected_factors',
            getattr(detail, 'connected_factors', None),
        )
        _require(
            errors,
            'detail.communicating',
            getattr(detail, 'communicating', None),
        )
        _require(
            errors,
            'detail.understanding_now',
            getattr(detail, 'understanding_now', None),
        )
    elif reflection.format == Reflection.FORMAT_FREE:
        _require(errors, 'title', reflection.title)
        detail = getattr(reflection, 'free_detail', None)
        _require(errors, 'detail.body', getattr(detail, 'body', None))

    contacts = set(reflection.contacts.values_list('id', flat=True))
    if reflection.primary_contact_id and reflection.primary_contact_id not in contacts:
        errors['primary_contact_id'] = (
            'Primary contact must also be included in contact_ids.'
        )


def complete_journal(journal):
    '''Validate and atomically complete a locked Log or Reflection.'''

    if journal.status == journal.STATUS_COMPLETED:
        return journal
    errors = completion_errors(journal)
    if errors:
        raise ValidationError(errors)
    if isinstance(journal, Reflection):
        publish_carry_forward(journal)
    journal.status = journal.STATUS_COMPLETED
    journal.completed_at = timezone.now()
    journal.current_step = 'review'
    journal.revision += 1
    journal.save(
        update_fields=[
            'status',
            'completed_at',
            'current_step',
            'revision',
            'updated_timestamp',
        ]
    )
    return journal


@transaction.atomic
def publish_carry_forward(reflection):
    '''Idempotently publish a Reflection's staged canonical context.'''

    created_counts = {'facts': 0, 'observations': 0}
    valid_observation_types = {choice[0] for choice in OBSERVATION_TYPE_CHOICES}
    valid_observation_statuses = {choice[0] for choice in OBSERVATION_STATUS_CHOICES}
    for draft in reflection.fact_drafts.select_for_update().all():
        fact, was_created = Fact.objects.get_or_create(
            source_reflection=reflection,
            source_item_id=draft.id,
            defaults={
                'contact': draft.target_contact,
                'category': draft.category,
                'label': draft.label or None,
                'detail_value': draft.detail_value,
                'is_conversation_cue': draft.is_conversation_cue,
            },
        )
        created_counts['facts'] += int(was_created)
        if draft.published_fact_id != fact.id:
            draft.published_fact = fact
            draft.save(update_fields=['published_fact'])

    for draft in reflection.observation_drafts.select_for_update().all():
        observation_type = (
            draft.observation_type
            if draft.observation_type in valid_observation_types
            else None
        )
        status = (
            draft.status
            if draft.status in valid_observation_statuses
            else 'current'
        )
        observation, was_created = Observation.objects.get_or_create(
            source_reflection=reflection,
            source_item_id=draft.id,
            defaults={
                'contact': draft.target_contact,
                'marker': draft.marker,
                'body': draft.body,
                'event': draft.event,
                'observation_type': observation_type,
                'status': status,
                'occurred_at': draft.occurred_at or reflection.occurred_at,
            },
        )
        created_counts['observations'] += int(was_created)
        if draft.published_observation_id != observation.id:
            draft.published_observation = observation
            draft.save(update_fields=['published_observation'])
    return created_counts
