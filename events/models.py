import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from users.models import Users
from contacts.models import Contact
from lookups.models import ContextCategory, InteractionMode, Mood
from django.utils import timezone

EVENT_TIER_ROUTINE = 'routine'
EVENT_TIER_MILESTONE = 'milestone'
EVENT_IMPACT_NEGATIVE = 'negative'
EVENT_IMPACT_NEUTRAL = 'neutral'
EVENT_IMPACT_POSITIVE = 'positive'

EVENT_TIER_CHOICES = [
    (EVENT_TIER_ROUTINE, 'Routine'),
    (EVENT_TIER_MILESTONE, 'Milestone'),
]

EVENT_IMPACT_CHOICES = [
    (EVENT_IMPACT_NEGATIVE, 'Negative'),
    (EVENT_IMPACT_NEUTRAL, 'Neutral'),
    (EVENT_IMPACT_POSITIVE, 'Positive'),
]

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
    Current Journals are linked by Log and Reflection models.
    '''
    user = models.ForeignKey(
        Users,
        on_delete = models.CASCADE,
        related_name = 'events',
    ) 
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_timestamp = models.DateTimeField()
    end_timestamp = models.DateTimeField(null=True, blank=True)
    location_label = models.CharField(max_length=255, blank=True)
    tier = models.CharField(
        max_length=20,
        choices=EVENT_TIER_CHOICES,
        default=EVENT_TIER_ROUTINE,
    )
    impact = models.CharField(
        max_length=20,
        choices=EVENT_IMPACT_CHOICES,
        blank=True,
    )
    context_category = models.ForeignKey(
        ContextCategory,
        null=True,
        blank=True,
        on_delete = models.SET_NULL,
        related_name = 'events',
    )
    interaction_mode = models.ForeignKey(
        InteractionMode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='events',
    )
    mood = models.ForeignKey(
        Mood,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='events',
    )
    objects = EventManager()

    class Meta:
        db_table = 'events'
        ordering = ['-event_timestamp']

    @property
    def journaled(self):
        annotated_logs = getattr(self, 'journal_log_exists', None)
        annotated_reflections = getattr(
            self,
            'journal_reflection_exists',
            None,
        )
        if annotated_logs is not None and annotated_reflections is not None:
            return bool(annotated_logs or annotated_reflections)
        return self.logs.exists() or self.reflections.exists()
    
    def __str__(self):
        return f'{self.title} ({self.event_timestamp: %Y-%m-%d})'


class EventParticipant(models.Model):
    '''
    Junction model links Events to Contacts
    Allows multiple contacts to be tagged to a single event.
    Deleting either (event or contact) cascades and deletes junction row.
    Interaction metric signals run on save/delete for the linked contact.
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


class EventChapter(models.Model):
    '''An explicitly ordered part of an Event's story.'''

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='chapters',
    )
    title = models.CharField(max_length=120)
    position = models.PositiveIntegerField()
    start_timestamp = models.DateTimeField(null=True, blank=True)
    end_timestamp = models.DateTimeField(null=True, blank=True)
    location_label = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    inherits_event_participants = models.BooleanField(default=True)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'event_chapters'
        ordering = ['position', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'position'],
                name='unique_event_chapter_position',
            ),
            models.CheckConstraint(
                condition=(
                    Q(start_timestamp__isnull=True)
                    | Q(end_timestamp__isnull=True)
                    | Q(end_timestamp__gte=models.F('start_timestamp'))
                ),
                name='event_chapter_end_not_before_start',
            ),
        ]
        indexes = [
            models.Index(
                fields=['event', 'position', 'id'],
                name='event_chapter_order_idx',
            ),
        ]

    def __str__(self):
        return f'{self.event}: {self.title}'


class EventChapterParticipant(models.Model):
    '''An explicitly ordered participant used when a chapter opts out of inheritance.'''

    chapter = models.ForeignKey(
        EventChapter,
        on_delete=models.CASCADE,
        related_name='participant_links',
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='event_chapter_participations',
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'event_chapter_participants'
        ordering = ['display_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['chapter', 'contact'],
                name='unique_event_chapter_contact',
            ),
            models.UniqueConstraint(
                fields=['chapter', 'display_order'],
                name='unique_event_chapter_contact_order',
            ),
        ]

    def __str__(self):
        return f'{self.contact} @ {self.chapter}'


class EventMedia(models.Model):
    '''An ordered, presentation-specific association between an Event and media.'''

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='media_attachments',
    )
    chapter = models.ForeignKey(
        EventChapter,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='media_attachments',
    )
    media_asset = models.ForeignKey(
        'media.MediaAsset',
        on_delete=models.PROTECT,
        related_name='event_attachments',
    )
    display_order = models.PositiveIntegerField()
    recorded_at = models.DateTimeField(null=True, blank=True)
    alt_text = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True)
    decorative = models.BooleanField(default=False)
    is_cover = models.BooleanField(default=False)
    focal_x = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        default=Decimal('0.50000'),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    focal_y = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        default=Decimal('0.50000'),
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'event_media'
        ordering = ['display_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'media_asset'],
                condition=Q(chapter__isnull=True),
                name='unique_whole_event_media_asset',
            ),
            models.UniqueConstraint(
                fields=['chapter', 'media_asset'],
                condition=Q(chapter__isnull=False),
                name='unique_chapter_media_asset',
            ),
            models.UniqueConstraint(
                fields=['event', 'display_order'],
                condition=Q(chapter__isnull=True),
                name='unique_whole_event_media_order',
            ),
            models.UniqueConstraint(
                fields=['chapter', 'display_order'],
                condition=Q(chapter__isnull=False),
                name='unique_chapter_media_order',
            ),
            models.UniqueConstraint(
                fields=['event'],
                condition=Q(chapter__isnull=True, is_cover=True),
                name='unique_whole_event_media_cover',
            ),
            models.UniqueConstraint(
                fields=['chapter'],
                condition=Q(chapter__isnull=False, is_cover=True),
                name='unique_chapter_media_cover',
            ),
            models.CheckConstraint(
                condition=Q(focal_x__gte=0, focal_x__lte=1),
                name='event_media_focal_x_normalized',
            ),
            models.CheckConstraint(
                condition=Q(focal_y__gte=0, focal_y__lte=1),
                name='event_media_focal_y_normalized',
            ),
        ]
        indexes = [
            models.Index(
                fields=['event', 'chapter', 'display_order'],
                name='event_media_scope_order_idx',
            ),
        ]

    def __str__(self):
        scope = self.chapter or self.event
        return f'{self.media_asset} @ {scope}'


class EventMediaCrop(models.Model):
    '''A non-destructive normalized crop for one Event media presentation.'''

    KIND_EVENT_COVER = 'event_cover'
    KIND_CHAPTER_CAROUSEL = 'chapter_carousel'
    KIND_CHOICES = [
        (KIND_EVENT_COVER, 'Event cover'),
        (KIND_CHAPTER_CAROUSEL, 'Chapter carousel'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_media = models.ForeignKey(
        EventMedia,
        on_delete=models.CASCADE,
        related_name='crops',
    )
    crop_kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    x = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    y = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    width = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        validators=[MinValueValidator(Decimal('0.00001')), MaxValueValidator(1)],
    )
    height = models.DecimalField(
        max_digits=6,
        decimal_places=5,
        validators=[MinValueValidator(Decimal('0.00001')), MaxValueValidator(1)],
    )
    source_orientation_revision = models.PositiveIntegerField(default=1)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'event_media_crops'
        ordering = ['crop_kind', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['event_media', 'crop_kind'],
                name='unique_event_media_crop_kind',
            ),
            models.CheckConstraint(
                condition=Q(x__gte=0, x__lte=1),
                name='event_media_crop_x_normalized',
            ),
            models.CheckConstraint(
                condition=Q(y__gte=0, y__lte=1),
                name='event_media_crop_y_normalized',
            ),
            models.CheckConstraint(
                condition=Q(width__gt=0, width__lte=1),
                name='event_media_crop_width_normalized',
            ),
            models.CheckConstraint(
                condition=Q(height__gt=0, height__lte=1),
                name='event_media_crop_height_normalized',
            ),
        ]

    def __str__(self):
        return f'{self.event_media}: {self.crop_kind}'
