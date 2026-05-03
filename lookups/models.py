from django.db import models
from django.db.models import Q
from core.constants import MOOD_POLARITY_CHOICES, MOOD_POLARITY_NEUTRAL
from users.models import Users

class LookupManager(models.Manager):
    '''
    Shared manager for all lookup tables that support both system defaults
    and user-defined rows. Returns system defaults (user_id=NULL) unioned
    with rows owned by the requesting user.
    '''
    def for_user(self, user):
        return self.get_queryset().filter(
            Q(user_id=user) | Q(is_system_default=True)
        )

class Occupation(models.Model):
    '''
    Lookup table for contact occupation options.
    System defaults (is_system_default=True) are seeded via data migration.
    Users can create custom occupations tied to their user_id.
    '''
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='occupations'
    )
    name = models.CharField(max_length=255)
    is_system_default = models.BooleanField(default=False)

    objects = LookupManager()

    class Meta:
        db_table = 'occupations'
    
    def __str__(self):
        return self.name
    
class EducationLevel(models.Model):
    '''
    Lookup table for contact education level options.
    System defaults seeded via data migration.
    Users can create custom education levels tied to their user_id.
    '''
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='education_levels'
    )
    name = models.CharField(max_length=255)
    is_system_default = models.BooleanField(default=False)

    objects = LookupManager()

    class Meta:
        db_table = 'education_levels'

    def __str__(self):
        return self.name

class Relation(models.Model):
    '''
    Lookup table for how a contact relates to the requesting user.
    System defaults are seeded via data migration.
    Users can create custom relations tied to their user_id in a later UI pass.
    '''
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='relations'
    )
    name = models.CharField(max_length=100)
    is_system_default = models.BooleanField(default=False)

    objects = LookupManager()

    class Meta:
        db_table = 'relations'

    def __str__(self):
        return self.name
    
class Mood(models.Model):
    '''
    Lookup table for event mood tags (Happy, Neutral, Sad, Angry).
    System defaults seeded via data migration.
    Users can create custom moods tied to their user_id.
    '''
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='moods'
    )
    name = models.CharField(max_length=100)
    emoji_icon = models.CharField(max_length=10)
    polarity = models.IntegerField(
        choices=MOOD_POLARITY_CHOICES,
        default=MOOD_POLARITY_NEUTRAL,
    )
    is_system_default = models.BooleanField(default=False)

    objects = LookupManager()

    class Meta:
        db_table = 'moods'

    def __str__(self):
        return f'{self.emoji_icon} {self.name}'
    
class ContextCategory(models.Model):
    '''
    Lookup table for event context categories (Social, Professional, Family).
    System defaults seeded via data migration.
    Users can create custom categories tied to their user_id.
    '''
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='context_categories'
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7)
    is_system_default = models.BooleanField(default=False)

    objects = LookupManager()

    class Meta:
        db_table = 'context_categories'

    def __str__(self):
        return self.name
    
class FactCategory(models.Model):
    '''
    Self-referencing lookup tree for contact fact categories.
    Examples: Health > Allergies > Food Allergies.
    parent_id=NULL indicates a root-level category.
    System defaults seeded via data migration.
    Users can create custom categories tied to their user_id.
    '''
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='fact_categories'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    name = models.CharField(max_length=255)
    icon_reference = models.CharField(max_length=100, blank=True)
    is_system_default = models.BooleanField(default=False)

    objects = LookupManager()

    class Meta:
        db_table = 'fact_categories'

    def __str__(self):
        return self.name
    
class EntryTag(models.Model):
    """
    User-defined or system-default tags that can be applied to entries.
    Follows the same is_system_default pattern as other lookup models.
    """
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        null=True, 
        blank=True,
        related_name="entry_tags",
    )
    tag_name = models.CharField(max_length=100)
    is_system_default = models.BooleanField(default=False)

    objects = LookupManager()

    class Meta:
        db_table = "entry_tags"

    def __str__(self):
        return self.tag_name
    
class ObservationMarker(models.Model):
    '''
    Lookup table for contact observation marker styles.
    Controls the visual appearance of observation cards on the contact profile.
    System defaults seeded via data migration.
    Users can create custom markers tied to their user_id.
    '''
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='observation_markers'
    )
    name = models.CharField(max_length=100)
    color_hex = models.CharField(max_length=7)
    icon_reference = models.CharField(max_length=100, blank=True)
    is_system_default = models.BooleanField(default=False)

    objects = LookupManager()

    class Meta:
        db_table = 'observation_markers'

    def __str__(self):
        return self.name
    
class MediaType(models.Model):
    '''
    Lookup table for media attachment types (IMAGE, VIDEO, AUDIO, DOCUMENT).
    Read-only — system defaults only, no user_id FK.
    Seeded via data migration.
    '''
    name = models.CharField(max_length=50)
    is_system_default = models.BooleanField(default=True)

    class Meta:
        db_table = 'media_types'

    def __str__(self):
        return self.name
