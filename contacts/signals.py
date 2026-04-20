from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

@receiver(post_save, sender='events.EventParticipant')
def recalculate_closeness(sender, instance, **kwargs):
    '''
    fires on every EventParticipant post_save call.
    Queries all events that the associated contact has participated in.
    Determines the most recent interaction and updates closeness of contact accordingly.
        High = interacted within last 14 days
        Medium = interacted within last 30 days
        Low = no interactions in last 30 days or more
    Utilizes string reference 'events.EventParticipant' as the sender to
    avoid circular import between contacts and events apps.
    '''
    from lookups.models import ClosenessScore
    from contacts.models import Contact

    contact = instance.contact
    now = timezone.now()

    most_recent = (
        instance.contact.events_participants
            .select_related('event')
            .order_by('-event__event_timestamp')
            .values_list('event__event_timestamp', flat=True)
            .first()
    )

    if (most_recent and most_recent >= (now - timedelta(days=14))):
        score_name = 'High'
    elif (most_recent and most_recent >= (now - timedelta(days=30))):
        score_name = 'Medium'
    else:
        score_name = 'Low'

    try:
        closeness_score = ClosenessScore.objects.filter(name=score_name).first()
        Contact.objects.filter(pk=contact.pk).update(
            closeness_score=closeness_score
        )
    except ClosenessScore.DoesNotExist:
        # ClosenessScore lookup rows have not been seeded, skipping for now
        pass
