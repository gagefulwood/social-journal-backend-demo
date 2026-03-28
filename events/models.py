from django.db import models
from users.models import Users
from contacts.models import Contact
from lookups.models import ContextCategory
from django.utils import timezone

class EventManager(models.Manager):
    def upcoming(self, user):
        return self.filter(
            user=user,
            event_timestamp__gt=timezone.now()
        ).order_by('event_timestamp')[:5]

    def recent(self, user):
        return self.filter(
            user=user,
            event_timestamp__lte=timezone.now()
        ).order_by('-event_timestamp')[:5]

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

class EventParticipant(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)