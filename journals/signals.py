from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


def recalculate_event_contacts(event_id):
    from contacts.services import recalculate_contact_statistics
    from events.models import EventParticipant

    participants = EventParticipant.objects.filter(event_id=event_id).select_related(
        'contact'
    )
    for participant in participants:
        recalculate_contact_statistics(participant.contact)


@receiver(post_save, sender='journals.Log')
def recalculate_interaction_metrics_on_log_save(sender, instance, **kwargs):
    '''
    Recalculate contact statistics when a log mood changes.
    '''
    recalculate_event_contacts(instance.event_id)


@receiver(post_delete, sender='journals.Log')
def recalculate_interaction_metrics_on_log_delete(sender, instance, **kwargs):
    '''
    Recalculate contact statistics when a log is removed.
    '''
    recalculate_event_contacts(instance.event_id)
