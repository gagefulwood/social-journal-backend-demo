from django.contrib import admin
from .models import Event, EventParticipant

class EventParticipantInline(admin.TabularInline):
    model = EventParticipant
    extra = 0

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    '''
    Event admin with inline participants so all event data is 
    visible and editable from one page
    '''
    list_display = [
        'title',
        'user_email',
        'event_timestamp',
        'end_timestamp',
        'tier',
        'context_category',
    ]
    search_fields = ['title', 'location_label', 'user__email']
    list_filter = ['tier', 'context_category__name']
    inlines = [EventParticipantInline]

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def context_category_name(self, obj):
        return obj.context_category.name if obj.context_category else '-'
    context_category_name.short_description = 'Category'

@admin.register(EventParticipant)
class EventParticipantAdmin(admin.ModelAdmin):
    list_display = ['event', 'contact']
    search_fields = ['event__title', 'contact__first_name', 'contact__last_name']
