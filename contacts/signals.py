from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from contacts.services import recalculate_contact_statistics


@receiver(post_save, sender='events.EventParticipant')
def recalculate_interaction_metrics_on_participant_save(sender, instance, **kwargs):
    '''
    Recalculate relationship statistics when a contact is added to an event.
    '''
    recalculate_contact_statistics(instance.contact)


@receiver(post_delete, sender='events.EventParticipant')
def recalculate_interaction_metrics_on_participant_delete(sender, instance, **kwargs):
    '''
    Recalculate relationship statistics when a contact is removed from an event.
    '''
    recalculate_contact_statistics(instance.contact)
