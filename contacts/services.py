from django.utils import timezone

from core.constants import (
    CONNECTION_STRENGTH_WEIGHTS,
    INTERACTION_FREQUENCY_BUCKETS,
    INTERACTION_FREQUENCY_MULTIPLIER,
    MAX_RELATIONSHIP_SCORE,
    MOOD_POLARITY_NEGATIVE,
    MOOD_POLARITY_NEUTRAL,
    MOOD_POLARITY_POSITIVE,
    RELATIONSHIP_TREND_DORMANT,
    RELATIONSHIP_TREND_FADING,
    RELATIONSHIP_TREND_GROWING,
    RELATIONSHIP_TREND_SCORES,
    RELATIONSHIP_TREND_STABLE,
)


def calculate_interaction_frequency_score(events, now=None):
    now = now or timezone.now()
    score = 0
    for event in events:
        age_days = (now - event.event_timestamp).days
        if age_days < 0:
            continue
        # Recent interactions carry more weight; the bucket constants keep the
        # product tuning knobs out of the calculation code.
        for max_days, weight in INTERACTION_FREQUENCY_BUCKETS:
            if age_days <= max_days:
                score += weight
                break
    return min(score * INTERACTION_FREQUENCY_MULTIPLIER, MAX_RELATIONSHIP_SCORE)


def calculate_relationship_trend(events, now=None):
    now = now or timezone.now()
    current_count = 0
    previous_count = 0
    for event in events:
        age_days = (now - event.event_timestamp).days
        if age_days < 0:
            continue
        if age_days <= 30:
            current_count += 1
        elif age_days <= 60:
            previous_count += 1

    # Trend compares the last 30 days against the previous 30-day window.
    if current_count == 0:
        return RELATIONSHIP_TREND_DORMANT
    if current_count > previous_count:
        return RELATIONSHIP_TREND_GROWING
    if current_count < previous_count:
        return RELATIONSHIP_TREND_FADING
    return RELATIONSHIP_TREND_STABLE


def calculate_interaction_diversity_score(events, total_context_category_count):
    if total_context_category_count == 0:
        return 0

    # Diversity is measured against all available context categories, not only
    # categories the user has used before.
    category_ids = {
        event.context_category_id
        for event in events
        if event.context_category_id is not None
    }
    return min(
        round((len(category_ids) / total_context_category_count) * 100),
        MAX_RELATIONSHIP_SCORE,
    )


def calculate_sentiment_profile(events):
    from journals.models import Log

    event_ids = [event.id for event in events]
    if not event_ids:
        return {}

    # Logs are the only MVP journal kind with a normalized mood FK. Reflection
    # and Exercise sentiment mapping is deferred until their data is normalized.
    profile = {}
    logs = Log.objects.filter(event_id__in=event_ids, mood__isnull=False).select_related(
        'mood'
    )
    for log in logs:
        key = normalize_mood_name(log.mood.name)
        profile[key] = profile.get(key, 0) + 1
    return profile


def normalize_mood_name(name):
    # Store stable frontend-friendly keys without spaces or case differences.
    return ''.join(name.lower().split())


def calculate_sentiment_score(events):
    from journals.models import Log

    event_ids = [event.id for event in events]
    if not event_ids:
        return 0

    logs = Log.objects.filter(event_id__in=event_ids, mood__isnull=False).select_related(
        'mood'
    )
    total = logs.count()
    if total == 0:
        return 0

    # Sentiment score uses database-backed Mood.polarity; the stored profile
    # remains a simple mood-name -> count map for the frontend.
    weighted = 0
    for log in logs:
        if log.mood.polarity == MOOD_POLARITY_POSITIVE:
            weighted += 100
        elif log.mood.polarity == MOOD_POLARITY_NEUTRAL:
            weighted += 50
        elif log.mood.polarity == MOOD_POLARITY_NEGATIVE:
            weighted += 0
        else:
            weighted += 50
    return round(weighted / total)


def calculate_connection_strength(
    interaction_frequency_score,
    relationship_trend,
    interaction_diversity_score,
    sentiment_score,
):
    trend_score = RELATIONSHIP_TREND_SCORES[relationship_trend]
    return round(
        interaction_frequency_score
        * CONNECTION_STRENGTH_WEIGHTS['interaction_frequency_score']
        + trend_score * CONNECTION_STRENGTH_WEIGHTS['relationship_trend']
        + interaction_diversity_score
        * CONNECTION_STRENGTH_WEIGHTS['interaction_diversity_score']
        + sentiment_score * CONNECTION_STRENGTH_WEIGHTS['sentiment_profile']
    )


def calculate_contact_statistics(contact, now=None):
    from lookups.models import ContextCategory

    # Pull the event objects once so each pure calculation receives the same
    # event set and can be tested independently.
    participants = contact.events_participants.select_related(
        'event',
        'event__context_category',
    )
    events = [participant.event for participant in participants]
    total_context_category_count = ContextCategory.objects.count()

    interaction_frequency_score = calculate_interaction_frequency_score(
        events,
        now=now,
    )
    relationship_trend = calculate_relationship_trend(events, now=now)
    interaction_diversity_score = calculate_interaction_diversity_score(
        events,
        total_context_category_count,
    )
    sentiment_profile = calculate_sentiment_profile(events)
    sentiment_score = calculate_sentiment_score(events)
    connection_strength = calculate_connection_strength(
        interaction_frequency_score,
        relationship_trend,
        interaction_diversity_score,
        sentiment_score,
    )

    return {
        'interaction_frequency_score': interaction_frequency_score,
        'relationship_trend': relationship_trend,
        'interaction_diversity_score': interaction_diversity_score,
        'sentiment_profile': sentiment_profile,
        'connection_strength': connection_strength,
    }


def recalculate_contact_statistics(contact, now=None):
    from contacts.models import Contact

    statistics = calculate_contact_statistics(contact, now=now)
    # Use update() so signal-triggered recalculation does not call Contact.save()
    # and create recursive signal behavior later.
    Contact.objects.filter(pk=contact.pk).update(**statistics)
    return statistics
