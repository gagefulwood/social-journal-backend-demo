import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
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
    preferred_name = models.CharField(max_length=150, blank=True)
    gender_identity = models.CharField(max_length=150, blank=True)
    pronouns = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    met_through = models.CharField(max_length=255, blank=True)
    met_location = models.CharField(max_length=255, blank=True)

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

    def clean(self):
        super().clean()
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValidationError({
                    'timezone': 'Enter a valid IANA time zone.'
                }) from exc


class ContactMethod(models.Model):
    KIND_EMAIL = 'email'
    KIND_PHONE = 'phone'
    KIND_CHOICES = [
        (KIND_EMAIL, 'Email'),
        (KIND_PHONE, 'Phone'),
    ]

    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='contact_methods',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    label = models.CharField(max_length=80, blank=True)
    value = models.CharField(max_length=320)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = 'contact_methods'
        ordering = ['kind', '-is_primary', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['contact', 'kind'],
                condition=Q(is_primary=True),
                name='unique_primary_contact_method_kind',
            ),
        ]

    def clean(self):
        super().clean()
        if self.kind == self.KIND_EMAIL:
            validate_email(self.value)
        elif (
            self.kind == self.KIND_PHONE
            and (
                not re.fullmatch(r'^\+?[0-9().\- xX]{7,32}$', self.value)
                or len(re.sub(r'\D', '', self.value)) < 7
            )
        ):
            raise ValidationError({'value': 'Enter a valid phone number.'})


class ContactAddress(models.Model):
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='addresses',
    )
    label = models.CharField(max_length=80, blank=True)
    line_1 = models.CharField(max_length=255)
    line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = 'contact_addresses'
        ordering = ['-is_primary', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['contact'],
                condition=Q(is_primary=True),
                name='unique_primary_contact_address',
            ),
        ]

    def clean(self):
        super().clean()
        self.country_code = self.country_code.upper()
        if self.country_code and (
            len(self.country_code) != 2 or not self.country_code.isalpha()
        ):
            raise ValidationError({
                'country_code': 'Use a two-letter country code.'
            })


class ContactEmployment(models.Model):
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='employment',
    )
    title = models.CharField(max_length=255)
    organization = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)

    class Meta:
        db_table = 'contact_employment'
        ordering = ['-is_current', '-start_date', 'id']

    def clean(self):
        super().clean()
        _validate_profile_date_range(self.start_date, self.end_date, self.is_current)


class ContactEducation(models.Model):
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='education',
    )
    credential = models.CharField(max_length=255, blank=True)
    field_of_study = models.CharField(max_length=255, blank=True)
    institution = models.CharField(max_length=255)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)

    class Meta:
        db_table = 'contact_education'
        ordering = ['-is_current', '-start_date', 'id']

    def clean(self):
        super().clean()
        _validate_profile_date_range(self.start_date, self.end_date, self.is_current)


def _validate_profile_date_range(start_date, end_date, is_current):
    if start_date and end_date and end_date < start_date:
        raise ValidationError({
            'end_date': 'End date must be on or after start date.'
        })
    if is_current and end_date:
        raise ValidationError({
            'end_date': 'A current entry cannot have an end date.'
        })

class PinnableContextModel(models.Model):
    pinned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_pinned(self):
        return self.pinned_at is not None

    def pin(self):
        if self.pinned_at is None:
            self.pinned_at = timezone.now()
            self.save(update_fields=['pinned_at'])
        return self

    def unpin(self):
        if self.pinned_at is not None:
            self.pinned_at = None
            self.save(update_fields=['pinned_at'])
        return self


class Fact(PinnableContextModel):
    '''
    Structured, categorized information known about a contact.
    category_id references a node in FactCategory.
    label stores an optional concise key for the fact.
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
    label = models.CharField(max_length=120, null=True, blank=True)
    detail_value = models.TextField()
    is_conversation_cue = models.BooleanField(default=False)

    class Meta:
        db_table = 'facts'
        ordering = ['id']
        indexes = [
            models.Index(
                fields=['contact', '-pinned_at'],
                name='fact_contact_pinned_idx',
            ),
        ]

    def __str__(self):
        return f'{self.contact} - {self.category}: {self.detail_value}'

class Observation(PinnableContextModel):
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
        indexes = [
            models.Index(
                fields=['contact', '-pinned_at'],
                name='obs_contact_pinned_idx',
            ),
        ]
    
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
