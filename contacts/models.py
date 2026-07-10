from django.db import models
from django.db.models import Q
from django.utils import timezone
from core.constants import (
    RELATIONSHIP_TREND_CHOICES,
    RELATIONSHIP_TREND_DORMANT,
)
from users.models import Users
from lookups.models import (
    Occupation,
    EducationLevel,
    Relation,
    FactCategory,
    ObservationMarker,
)


OBSERVATION_TYPE_NOTICE = 'notice'
OBSERVATION_TYPE_CONVERSATION_CUE = 'conversation_cue'
OBSERVATION_TYPE_APPRECIATION = 'appreciation'
OBSERVATION_TYPE_CHANGE = 'change'

OBSERVATION_TYPE_CHOICES = [
    (OBSERVATION_TYPE_NOTICE, 'Notice'),
    (OBSERVATION_TYPE_CONVERSATION_CUE, 'Conversation cue'),
    (OBSERVATION_TYPE_APPRECIATION, 'Appreciation'),
    (OBSERVATION_TYPE_CHANGE, 'Change'),
]

OBSERVATION_STATUS_CURRENT = 'current'
OBSERVATION_STATUS_REVISIT_LATER = 'revisit_later'
OBSERVATION_STATUS_ARCHIVED = 'archived'

OBSERVATION_STATUS_CHOICES = [
    (OBSERVATION_STATUS_CURRENT, 'Current'),
    (OBSERVATION_STATUS_REVISIT_LATER, 'Revisit later'),
    (OBSERVATION_STATUS_ARCHIVED, 'Archived'),
]

class ContactManager(models.Manager):
    '''
    Custom contact manager for contact model.
    for_user() scopes queries requesting the user's contacts only.
    prevents cross-user data leaks.
    '''
    def for_user(self, user):
        return self.get_queryset().filter(user=user, is_active=True)

class ObservationManager(models.Manager):
    '''
    Custom manager for Observation.
    for_user() scopes observations to contacts owned by the requesting user.
    '''
    def for_user(self, user):
        return self.get_queryset().filter(
            contact__user=user,
            contact__is_active=True,
        )

class Contact(models.Model):
    '''
    Core PRM model for contacts.
    Relationship statistic fields are recalculated from event participation.
    '''
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='contacts'
    )
    first_name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    address = models.TextField(blank=True)
    birthday = models.DateField(null=True, blank=True)
    first_met_date = models.DateField(null=True, blank=True)

    occupation = models.ForeignKey(
        Occupation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contacts'
    )
    relation = models.ForeignKey(
        Relation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contacts'
    )
    custom_occupation = models.CharField(max_length=255, blank=True)
    company = models.CharField(max_length=255, blank=True)

    education_level = models.ForeignKey(
        EducationLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contacts'
    )
    custom_education_level = models.CharField(max_length=255, blank=True)
    school = models.CharField(max_length=255, blank=True)
    profile_picture = models.ForeignKey(
        'media.MediaAsset',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profile_contacts',
    )

    interaction_frequency_score = models.IntegerField(default=0)
    relationship_trend = models.CharField(
        max_length=20,
        choices=RELATIONSHIP_TREND_CHOICES,
        default=RELATIONSHIP_TREND_DORMANT,
    )
    interaction_diversity_score = models.IntegerField(default=0)
    sentiment_profile = models.JSONField(default=dict, blank=True)
    connection_strength = models.IntegerField(default=0)
    objects = ContactManager()

    class Meta:
        db_table = 'contacts'
        ordering = ['first_name', 'last_name']
    
    def __str__(self):
        return f'{self.first_name} {self.last_name}'.strip()

class Fact(models.Model):
    '''
    Structured, categorized information known about a contact.
    category_id references a node in FactCategory.
    detail_value stores the literal content of the fact.
    '''
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='facts'
    )
    category = models.ForeignKey(
        FactCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='facts'
    )
    detail_value = models.TextField()
    is_conversation_cue = models.BooleanField(default=False)

    class Meta:
        db_table = 'facts'
        ordering = ['id']

    def __str__(self):
        return f'{self.contact} - {self.category}: {self.detail_value}'

class Observation(models.Model):
    '''
    Freeform observation attached to a contact and styled by an ObservationMarker.
    is_active allows soft-hiding observations without deleting them.
    Unlike journal entries, observations are mutable.
    '''
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='observations'
    )
    marker = models.ForeignKey(
        ObservationMarker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='observations'
    )
    body = models.TextField()
    created_timestamp = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    observation_type = models.CharField(
        max_length=32,
        choices=OBSERVATION_TYPE_CHOICES,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=OBSERVATION_STATUS_CHOICES,
        default=OBSERVATION_STATUS_CURRENT,
    )
    occurred_at = models.DateTimeField(null=True, blank=True)
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='observations',
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = ObservationManager()

    class Meta:
        db_table = 'observations'
        ordering = ['-created_timestamp']
    
    def __str__(self):
        return f'Observation for {self.contact} - {self.created_timestamp:%Y-%m-%d}'

    def save(self, *args, **kwargs):
        if self.status == OBSERVATION_STATUS_ARCHIVED:
            self.is_active = False
            if self.archived_at is None:
                self.archived_at = timezone.now()
        else:
            self.is_active = True
            self.archived_at = None

        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {
                'status',
                'is_active',
                'archived_at',
            }

        super().save(*args, **kwargs)
