from django.db import models
from users.models import Users
from contacts.models import Contact
from lookups.models import ContextCategory
from django.utils import timezone

# Create your models here.
class Event(models.Model):
    user_id = models.ForeignKey(
        Users,
        on_delete = models.CASCADE,
        related_name = 'events',
    ) 
    title = models.Charfield(max_length=255)
    event_timestamp = models.DateTimeField()
    context_category_id = models.ForeignKey(
        ContextCategory,
        null=True,
        blank=True,
        on_delete = models.SET_NULL,
        related_name = 'events',
    )