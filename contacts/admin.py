from django.contrib import admin
from .models import Contact, Fact, ContactLooseNote

class FactInline(admin.TabularInline):
    model = Fact
    extra = 0

class ContactLooseNoteInline(admin.TabularInline):
    model = ContactLooseNote
    extra = 0

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    '''
    Contact admin with inline facts and loose notes visible from one page.
    '''
    list_display = ['first_name', 'last_name', 'email', 'user', 'closeness_score']
    search_fields = ['first_name', 'last_name', 'email']
    list_filter = ['closeness_score']
    inlines = [FactInline, ContactLooseNoteInline]

@admin.register(ContactLooseNote)
class ContactLooseNoteAdmin(admin.ModelAdmin):
    list_display = ['contact', 'marker', 'created_timestamp', 'is_active']
    list_filter = ['is_active', 'marker']
    search_fields = ['contact__first_name', 'contact__last_name', 'body']
