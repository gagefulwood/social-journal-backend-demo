import uuid
from django.conf import settings
from django.db import models
from lookups.models import JournalTag

# Create your models here.

class JournalEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField(
        "events.Event", 
        on_delete=models.CASCADE, 
        related_name="journal_entry",
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    mood = models.ForeignKey(
        "lookups.Mood", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
    )
    entry_timestamp = models.DateTimeField(auto_now_add=True)
    is_immutable = models.BooleanField(default=False)
    tags = models.ManyToManyField(
        JournalTag, 
        blank=True, 
        related_name="entries",
    )

    class Meta:
        db_table = "journal_entries"
        ordering = ["-entry_timestamp"]

    def __str__(self):
        return self.title

class Reflection(models.Model):
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
    )
    journal_entry = models.ForeignKey(
        JournalEntry, 
        on_delete=models.CASCADE, 
        related_name="reflections",
    )
    body = models.TextField()
    created_timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reflections"
        ordering = ["created_timestamp"]

    def __str__(self):
        return f"Reflection for {self.journal_entry.title[:20]}"