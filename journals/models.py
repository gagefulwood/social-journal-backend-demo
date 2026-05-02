import uuid

from django.conf import settings
from django.db import models


class JournalManager(models.Manager):
    '''
    Shared manager for journal entries scoped to the requesting user.
    '''
    def for_user(self, user):
        return self.get_queryset().filter(user=user)


class JournalBase(models.Model):
    '''
    Abstract base for all journal kinds.
    No table is created for this model.
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='%(class)ss',
    )
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
    )
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    objects = JournalManager()

    class Meta:
        abstract = True


class Log(JournalBase):
    '''
    Flat journal entry for quick event logging.
    '''
    title = models.CharField(max_length=255)
    body = models.TextField()
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
        ordering = ['-created_timestamp']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'event'],
                name='unique_log_user_event',
            ),
        ]

    def __str__(self):
        return self.title


class Reflection(JournalBase):
    '''
    Structured reflection entry. Variant prose fields live in data.
    '''
    subtype = models.CharField(max_length=50, default='standard')
    clarity_check = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'reflections'
        ordering = ['-created_timestamp']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'event'],
                name='unique_reflection_user_event',
            ),
        ]

    def __str__(self):
        return f'Reflection for {self.event}'


class Exercise(JournalBase):
    '''
    Closed-loop exercise entry with pre/post measurements.
    '''
    subtype = models.CharField(max_length=50, default='standard')
    pre_measurement = models.IntegerField()
    post_measurement = models.IntegerField()

    class Meta:
        db_table = 'exercises'
        ordering = ['-created_timestamp']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'event'],
                name='unique_exercise_user_event',
            ),
        ]

    @property
    def measurement_delta(self):
        return self.post_measurement - self.pre_measurement

    def __str__(self):
        return f'Exercise for {self.event}'


class ExerciseStep(models.Model):
    '''
    Ordered prompt/response pair attached to an Exercise.
    '''
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
