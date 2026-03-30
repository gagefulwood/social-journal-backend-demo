from django.db import models
from users.models import Users
from contacts.models import Contact
from lookups.models import ContextCategory
from django.utils import timezone

class EventManager(models.Manager):
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

# Create your models here.
class Event(models.Model):
    user_id = models.ForeignKey(
        Users,
        on_delete = models.CASCADE,
        related_name = 'events',
    ) 
    title = models.CharField(max_length=255)
    event_timestamp = models.DateTimeField()
    context_category_id = models.ForeignKey(
        ContextCategory,
        null=True,
        blank=True,
        on_delete = models.SET_NULL,
        related_name = 'events',
    )
    objects = EventManager()

    class Meta:
        db_table = "events"
        ordering = ["-events_timestamp"]
    
    def __str__(self):
        return f'{self.title} ({self.event_timestamp: %Y-%m-%d})'


class EventParticipant(models.Model):
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