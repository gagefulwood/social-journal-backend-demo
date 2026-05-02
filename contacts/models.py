from django.db import models
from django.db.models import Q
from users.models import Users
from lookups.models import (
    Occupation,
    EducationLevel,
    ClosenessScore,
    DetailCategoryTree,
    NoteMarker,
)

class ContactManager(models.Manager):
    '''
    Custom contact manager for contact model.
    for_user() scopes queries requesting the user's contacts only.
    prevents cross-user data leaks.
    '''
    def for_user(self, user):
        return self.get_queryset().filter(user=user, is_active=True)

class Contact(models.Model):
    '''
    Core PRM model for contacts.
    closeness_score is an automatic calculation on event saves
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

    closeness_score = models.ForeignKey(
        ClosenessScore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contacts'
    )
    objects = ContactManager()

    class Meta:
        db_table = 'contacts'
        ordering = ['first_name', 'last_name']
    
    def __str__(self):
        return f'{self.first_name} {self.last_name}'.strip()

class ContactPersonalDetail(models.Model):
    '''
    Flexible key-value store for the unstructured custom personal details tied to a contact.
    category_id references a node in the DetailCategoryTree
    detail_value stores the literal content of the detail
    '''
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='personal_details'
    )
    category = models.ForeignKey(
        DetailCategoryTree,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contact_details'
    )
    detail_value = models.TextField()

    class Meta:
        db_table = 'contact_personal_details'

    def __str__(self):
        return f'{self.contact} - {self.category}: {self.detail_value}'

class ContactLooseNote(models.Model):
    '''
    Freeform notes attached to a contact and styled by a NoteMarker.
    is_active allows soft-hiding notes without deleting them.
    unlike journal entries the loose notes are mutable.
    '''
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='loose_notes'
    )
    marker = models.ForeignKey(
        NoteMarker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notes'
    )
    body = models.TextField()
    created_timestamp = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'contact_loose_notes'
        ordering = ['-created_timestamp']
    
    def __str__(self):
        return f'Note for {self.contact} - {self.created_timestamp:%Y-%m-%d}'
