from django.db import models
from users.models import Users
from contacts.models import Contact
from lookups.models import ContextCategory
from django.utils import timezone

class EventManager(models.Manager):
    '''
    Custom django manager for Event model.
    upcoming() returns next 5 events after current time (ascending)
    recent() returns last 5 events to current time (descending)
    Both functions restricted to current user
    '''
    def upcoming(self, user):
        return (
            self.get_queryset()
            .filter(user=user, event_timestamp__gt=timezone.now())   
            .order_by('event_timestamp')[:5]
        )

    def recent(self, user):
        return (
            self.get_queryset()
                .filter(user=user, event_timestamp__lte=timezone.now())
                .order_by('-event_timestamp')[:5]
        )

class Event(models.Model):
    '''
    Event model representing logged social event journals.
    context_category links with ContextCategory lookup (social, pofessional, family)
    Participants are linked with EventParticipant junction model
    Journal entries are linkedvia OneToOne FK to the JournalEntry model
    '''
    user = models.ForeignKey(
        Users,
        on_delete = models.CASCADE,
        related_name = 'events',
    ) 
    title = models.CharField(max_length=255)
    event_timestamp = models.DateTimeField()
    context_category = models.ForeignKey(
        ContextCategory,
        null=True,
        blank=True,
        on_delete = models.SET_NULL,
        related_name = 'events',
    )
    objects = EventManager()

    class Meta:
        db_table = 'events'
        ordering = ['-event_timestamp']
    
    def __str__(self):
        return f'{self.title} ({self.event_timestamp: %Y-%m-%d})'


class EventParticipant(models.Model):
    '''
    Junction model links Events to Contacts
    Allows multiple contacts to be tagged to a single event.
    Deleting either (event or contact) cascades and deletes junction row.
    RecalculateClosenessSignal runs on post_save for this model to update closeness of linked contact
    '''
    event = models.ForeignKey(
        Event, 
        on_delete=models.CASCADE,
        related_name = "participants",
    )
    contact = models.ForeignKey(
        Contact, 
        on_delete=models.CASCADE,
        related_name = "events_participants",
    )

    class Meta:
        db_table = "participants"
        unique_together = ['event', 'contact'] 

    def __str__(self):
        return f'{self.contact} @ {self.event}'