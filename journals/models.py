import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class JournalManager(models.Manager):
    '''Shared manager for owner-scoped journal records.'''

    def for_user(self, user):
        return self.get_queryset().filter(user=user)


class JournalBase(models.Model):
    '''Columns shared by retained legacy exercises and current journals.'''

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='%(class)ss',
    )
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)ss',
    )
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    objects = JournalManager()

    class Meta:
        abstract = True


class CanonicalJournalBase(JournalBase):
    '''Lifecycle, concurrency, and context shared by Logs and Reflections.'''

    STATUS_DRAFT = 'draft'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    chapter = models.ForeignKey(
        'events.EventChapter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)ss',
    )
    primary_contact = models.ForeignKey(
        'contacts.Contact',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='primary_%(class)ss',
    )
    occurred_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    current_step = models.CharField(max_length=50, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True


class Log(CanonicalJournalBase):
    '''A typed structured journal Log with legacy columns retained in place.'''

    FORMAT_LEGACY = 'legacy'
    FORMAT_EPISODE = 'episode'
    FORMAT_SOCIAL_ENERGY = 'social_energy'
    FORMAT_SENTIMENT = 'sentiment'
    FORMAT_CHOICES = [
        (FORMAT_LEGACY, 'Legacy'),
        (FORMAT_EPISODE, 'Episode'),
        (FORMAT_SOCIAL_ENERGY, 'Social energy'),
        (FORMAT_SENTIMENT, 'Sentiment'),
    ]

    format = models.CharField(
        max_length=30,
        choices=FORMAT_CHOICES,
        default=FORMAT_LEGACY,
    )
    title = models.CharField(max_length=255, blank=True)

    # Retained read-only compatibility columns for records created before the
    # typed Journal replacement.
    body = models.TextField(blank=True)
    mood = models.ForeignKey(
        'lookups.Mood',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs',
    )
    tags = models.ManyToManyField(
        'lookups.EntryTag',
        blank=True,
        related_name='logs',
    )
    subtype = models.CharField(max_length=50, default='standard')
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'logs'
        ordering = ['-updated_timestamp', '-created_timestamp']
        indexes = [
            models.Index(
                fields=['user', 'status', '-updated_timestamp'],
                name='log_owner_status_updated_idx',
            ),
            models.Index(
                fields=['user', 'format', '-occurred_at'],
                name='log_owner_format_occurred_idx',
            ),
            models.Index(
                fields=['user', 'chapter', 'status', '-occurred_at'],
                name='log_owner_chap_status_occ_idx',
            ),
        ]

    def __str__(self):
        return self.title or f'{self.get_format_display()} log'


class EpisodeLogDetail(models.Model):
    log = models.OneToOneField(
        Log,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='episode_detail',
    )
    category = models.ForeignKey(
        'lookups.EpisodeCategory',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='episode_logs',
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    is_ongoing = models.BooleanField(default=False)
    characteristics = models.ManyToManyField(
        'lookups.EpisodeCharacteristic',
        blank=True,
        related_name='episode_logs',
    )
    context_tags = models.ManyToManyField(
        'lookups.EpisodeContextTag',
        blank=True,
        related_name='episode_logs',
    )

    class Meta:
        db_table = 'episode_log_details'


class SocialEnergyLogDetail(models.Model):
    BEFORE_OPEN = 'open'
    BEFORE_NEUTRAL = 'neutral'
    BEFORE_RESERVED = 'reserved'
    BEFORE_DEPLETED = 'depleted'
    BEFORE_CHOICES = [
        (BEFORE_OPEN, 'Open'),
        (BEFORE_NEUTRAL, 'Neutral'),
        (BEFORE_RESERVED, 'Reserved'),
        (BEFORE_DEPLETED, 'Depleted'),
    ]
    BATTERY_REDUCED = 'reduced'
    BATTERY_UNCHANGED = 'unchanged'
    BATTERY_INCREASED = 'increased'
    BATTERY_CHOICES = [
        (BATTERY_REDUCED, 'Reduced'),
        (BATTERY_UNCHANGED, 'Unchanged'),
        (BATTERY_INCREASED, 'Increased'),
    ]
    MOOD_WORSE = 'worse'
    MOOD_UNCHANGED = 'unchanged'
    MOOD_IMPROVED = 'improved'
    MOOD_CHOICES = [
        (MOOD_WORSE, 'Worse'),
        (MOOD_UNCHANGED, 'Unchanged'),
        (MOOD_IMPROVED, 'Improved'),
    ]
    BEHAVIOR_QUIETER = 'quieter'
    BEHAVIOR_UNCHANGED = 'unchanged'
    BEHAVIOR_MORE_SOCIAL = 'more_social'
    BEHAVIOR_WITHDREW = 'withdrew'
    BEHAVIOR_CHOICES = [
        (BEHAVIOR_QUIETER, 'Quieter'),
        (BEHAVIOR_UNCHANGED, 'Unchanged'),
        (BEHAVIOR_MORE_SOCIAL, 'More social'),
        (BEHAVIOR_WITHDREW, 'Withdrew'),
    ]
    RECOVERY_NOT_YET = 'not_yet'
    RECOVERY_RIGHT_AWAY = 'right_away'
    RECOVERY_LATER_DAY = 'later_day'
    RECOVERY_NEXT_DAY = 'next_day'
    RECOVERY_CHOICES = [
        (RECOVERY_NOT_YET, 'Not yet'),
        (RECOVERY_RIGHT_AWAY, 'Right away'),
        (RECOVERY_LATER_DAY, 'Later that day'),
        (RECOVERY_NEXT_DAY, 'Next day'),
    ]
    CONTEXT_ONE_ON_ONE = 'one_on_one'
    CONTEXT_SMALL_GROUP = 'small_group'
    CONTEXT_LARGE_GROUP = 'large_group'
    CONTEXT_CHOICES = [
        (CONTEXT_ONE_ON_ONE, 'One-on-one'),
        (CONTEXT_SMALL_GROUP, 'Small group'),
        (CONTEXT_LARGE_GROUP, 'Large group'),
    ]
    FAMILIARITY_VERY = 'very_familiar'
    FAMILIARITY_FAMILIAR = 'familiar'
    FAMILIARITY_MIXED = 'mixed'
    FAMILIARITY_UNFAMILIAR = 'unfamiliar'
    FAMILIARITY_CHOICES = [
        (FAMILIARITY_VERY, 'Very familiar'),
        (FAMILIARITY_FAMILIAR, 'Familiar'),
        (FAMILIARITY_MIXED, 'Mixed'),
        (FAMILIARITY_UNFAMILIAR, 'Unfamiliar'),
    ]
    SETTING_STRUCTURED = 'structured'
    SETTING_UNSTRUCTURED = 'unstructured'
    SETTING_CHOICES = [
        (SETTING_STRUCTURED, 'Structured'),
        (SETTING_UNSTRUCTURED, 'Unstructured'),
    ]

    log = models.OneToOneField(
        Log,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='social_energy_detail',
    )
    before_state = models.CharField(
        max_length=20,
        choices=BEFORE_CHOICES,
        blank=True,
    )
    battery_effect = models.CharField(
        max_length=20,
        choices=BATTERY_CHOICES,
        blank=True,
    )
    mood_shift = models.CharField(max_length=20, choices=MOOD_CHOICES, blank=True)
    behavioral_effect = models.CharField(
        max_length=20,
        choices=BEHAVIOR_CHOICES,
        blank=True,
    )
    recovery_timing = models.CharField(
        max_length=20,
        choices=RECOVERY_CHOICES,
        blank=True,
    )
    interaction_context = models.CharField(
        max_length=20,
        choices=CONTEXT_CHOICES,
        blank=True,
    )
    group_size = models.PositiveSmallIntegerField(null=True, blank=True)
    familiarity = models.CharField(
        max_length=20,
        choices=FAMILIARITY_CHOICES,
        blank=True,
    )
    setting = models.CharField(max_length=20, choices=SETTING_CHOICES, blank=True)
    factors = models.ManyToManyField(
        'lookups.SocialEnergyFactor',
        blank=True,
        related_name='social_energy_logs',
    )

    class Meta:
        db_table = 'social_energy_log_details'


class SentimentLogDetail(models.Model):
    CONNECTION_CLOSE = 'close'
    CONNECTION_NEUTRAL = 'neutral'
    CONNECTION_DISTANT = 'distant'
    CONNECTION_CHOICES = [
        (CONNECTION_CLOSE, 'Close'),
        (CONNECTION_NEUTRAL, 'Neutral'),
        (CONNECTION_DISTANT, 'Distant'),
    ]
    INITIATED_ME = 'me'
    INITIATED_THEM = 'them'
    INITIATED_MUTUAL = 'mutual'
    INITIATED_CHOICES = [
        (INITIATED_ME, 'Me'),
        (INITIATED_THEM, 'Them'),
        (INITIATED_MUTUAL, 'Mutual'),
    ]
    EXCHANGE_POSITIVE = 'positive'
    EXCHANGE_NEUTRAL = 'neutral'
    EXCHANGE_NEGATIVE = 'negative'
    EXCHANGE_CHOICES = [
        (EXCHANGE_POSITIVE, 'Positive'),
        (EXCHANGE_NEUTRAL, 'Neutral'),
        (EXCHANGE_NEGATIVE, 'Negative'),
    ]

    log = models.OneToOneField(
        Log,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='sentiment_detail',
    )
    before_state = models.ForeignKey(
        'lookups.EmotionState',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sentiment_before_logs',
    )
    after_state = models.ForeignKey(
        'lookups.EmotionState',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sentiment_after_logs',
    )
    before_connection = models.CharField(
        max_length=20,
        choices=CONNECTION_CHOICES,
        blank=True,
    )
    after_connection = models.CharField(
        max_length=20,
        choices=CONNECTION_CHOICES,
        blank=True,
    )
    dynamics = models.ManyToManyField(
        'lookups.InteractionDynamic',
        blank=True,
        related_name='sentiment_logs',
    )
    initiated_by = models.CharField(
        max_length=20,
        choices=INITIATED_CHOICES,
        blank=True,
    )
    overall_exchange = models.CharField(
        max_length=20,
        choices=EXCHANGE_CHOICES,
        blank=True,
    )

    class Meta:
        db_table = 'sentiment_log_details'


class Reflection(CanonicalJournalBase):
    '''A typed Reflection with optional context, media, and carry-forward.'''

    FORMAT_LEGACY = 'legacy'
    FORMAT_INTERACTION = 'interaction'
    FORMAT_MOMENT = 'moment'
    FORMAT_EMOTIONAL = 'emotional'
    FORMAT_FREE = 'free'
    FORMAT_CHOICES = [
        (FORMAT_LEGACY, 'Legacy'),
        (FORMAT_INTERACTION, 'Interaction'),
        (FORMAT_MOMENT, 'Moment'),
        (FORMAT_EMOTIONAL, 'Emotional'),
        (FORMAT_FREE, 'Free reflection'),
    ]

    format = models.CharField(
        max_length=30,
        choices=FORMAT_CHOICES,
        default=FORMAT_LEGACY,
    )
    title = models.CharField(max_length=255, blank=True)
    contacts = models.ManyToManyField(
        'contacts.Contact',
        through='ReflectionContact',
        related_name='journal_reflections',
        blank=True,
    )
    cover_attachment = models.ForeignKey(
        'ReflectionAttachment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )

    # Retained compatibility columns for records created before this schema.
    subtype = models.CharField(max_length=50, default='standard')
    clarity_check = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'reflections'
        ordering = ['-updated_timestamp', '-created_timestamp']
        indexes = [
            models.Index(
                fields=['user', 'status', '-updated_timestamp'],
                name='refl_owner_status_updated_idx',
            ),
            models.Index(
                fields=['user', 'format', '-occurred_at'],
                name='refl_owner_format_occurr_idx',
            ),
            models.Index(
                fields=['user', 'chapter', 'status', '-occurred_at'],
                name='refl_owner_chap_stat_occ_idx',
            ),
        ]

    def __str__(self):
        return self.title or f'{self.get_format_display()} reflection'


class ReflectionContact(models.Model):
    reflection = models.ForeignKey(
        Reflection,
        on_delete=models.CASCADE,
        related_name='contact_links',
    )
    contact = models.ForeignKey(
        'contacts.Contact',
        on_delete=models.CASCADE,
        related_name='reflection_links',
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'reflection_contacts'
        ordering = ['display_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['reflection', 'contact'],
                name='unique_reflection_contact',
            ),
        ]


class InteractionReflectionDetail(models.Model):
    reflection = models.OneToOneField(
        Reflection,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='interaction_detail',
    )
    topic_or_activity = models.TextField(blank=True)
    user_actions = models.TextField(blank=True)
    contact_actions = models.TextField(blank=True)
    contact_response = models.TextField(blank=True)
    user_response = models.TextField(blank=True)
    feelings_now = models.TextField(blank=True)
    important_to_understand = models.TextField(blank=True)
    additional_writing = models.TextField(blank=True)

    class Meta:
        db_table = 'interaction_reflection_details'


class MomentReflectionDetail(models.Model):
    reflection = models.OneToOneField(
        Reflection,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='moment_detail',
    )
    focus_moment = models.TextField(blank=True)
    what_happened = models.TextField(blank=True)
    noticed_around = models.TextField(blank=True)
    response = models.TextField(blank=True)
    stood_out = models.TextField(blank=True)
    meaning_now = models.TextField(blank=True)
    remember = models.TextField(blank=True)
    additional_writing = models.TextField(blank=True)

    class Meta:
        db_table = 'moment_reflection_details'


class EmotionalReflectionDetail(models.Model):
    reflection = models.OneToOneField(
        Reflection,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='emotional_detail',
    )
    emotions = models.ManyToManyField(
        'lookups.EmotionState',
        blank=True,
        related_name='emotional_reflections',
    )
    situation = models.TextField(blank=True)
    connected_factors = models.TextField(blank=True)
    communicating = models.TextField(blank=True)
    understanding_now = models.TextField(blank=True)
    additional_writing = models.TextField(blank=True)

    class Meta:
        db_table = 'emotional_reflection_details'


class EmotionalManifestation(models.Model):
    KIND_THOUGHT = 'thought'
    KIND_BODY = 'body'
    KIND_BEHAVIOR = 'behavior'
    KIND_CHOICES = [
        (KIND_THOUGHT, 'Thought'),
        (KIND_BODY, 'Body'),
        (KIND_BEHAVIOR, 'Behavior'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    emotional_detail = models.ForeignKey(
        EmotionalReflectionDetail,
        on_delete=models.CASCADE,
        related_name='manifestations',
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    text = models.CharField(max_length=500)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'emotional_manifestations'
        ordering = ['display_order', 'id']


class FreeReflectionDetail(models.Model):
    reflection = models.OneToOneField(
        Reflection,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='free_detail',
    )
    body = models.TextField(blank=True)

    class Meta:
        db_table = 'free_reflection_details'


class ReflectionAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reflection = models.ForeignKey(
        Reflection,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    media_asset = models.ForeignKey(
        'media.MediaAsset',
        on_delete=models.PROTECT,
        related_name='reflection_attachments',
    )
    is_sensitive = models.BooleanField(default=False)
    recorded_at = models.DateTimeField(null=True, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'reflection_attachments'
        ordering = ['display_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['reflection', 'media_asset'],
                name='unique_reflection_media_asset',
            ),
        ]


class CarryForwardFactDraft(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reflection = models.ForeignKey(
        Reflection,
        on_delete=models.CASCADE,
        related_name='fact_drafts',
    )
    target_contact = models.ForeignKey(
        'contacts.Contact',
        on_delete=models.CASCADE,
        related_name='reflection_fact_drafts',
    )
    category = models.ForeignKey(
        'lookups.FactCategory',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reflection_fact_drafts',
    )
    label = models.CharField(max_length=120, blank=True)
    detail_value = models.TextField()
    is_conversation_cue = models.BooleanField(default=False)
    published_fact = models.OneToOneField(
        'contacts.Fact',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_carry_draft',
    )

    class Meta:
        db_table = 'carry_forward_fact_drafts'
        ordering = ['id']


class CarryForwardObservationDraft(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reflection = models.ForeignKey(
        Reflection,
        on_delete=models.CASCADE,
        related_name='observation_drafts',
    )
    target_contact = models.ForeignKey(
        'contacts.Contact',
        on_delete=models.CASCADE,
        related_name='reflection_observation_drafts',
    )
    marker = models.ForeignKey(
        'lookups.ObservationMarker',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reflection_observation_drafts',
    )
    body = models.TextField()
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reflection_observation_drafts',
    )
    observation_type = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=20, default='current')
    occurred_at = models.DateTimeField(null=True, blank=True)
    published_observation = models.OneToOneField(
        'contacts.Observation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_carry_draft',
    )

    class Meta:
        db_table = 'carry_forward_observation_drafts'
        ordering = ['id']


class Exercise(JournalBase):
    '''Retained for historical rows but intentionally hidden from Journal APIs.'''

    title = models.CharField(max_length=255)
    subtype = models.CharField(max_length=50, default='standard')
    pre_measurement = models.IntegerField()
    post_measurement = models.IntegerField()

    class Meta:
        db_table = 'exercises'
        ordering = ['-created_timestamp']

    @property
    def measurement_delta(self):
        return self.post_measurement - self.pre_measurement

    def __str__(self):
        return self.title


class ExerciseStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name='steps',
    )
    display_order = models.PositiveIntegerField()
    prompt = models.CharField(max_length=255)
    response = models.TextField()

    class Meta:
        db_table = 'exercise_steps'
        ordering = ['display_order']
        constraints = [
            models.UniqueConstraint(
                fields=['exercise', 'display_order'],
                name='unique_exercise_step_order',
            ),
        ]

    def __str__(self):
        return f'{self.exercise} step {self.display_order}'
