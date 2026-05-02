from django.contrib import admin
from .models import Contact, Fact, Observation

class FactInline(admin.TabularInline):
    model = Fact
    extra = 0

class ObservationInline(admin.TabularInline):
    model = Observation
    extra = 0

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    '''
    Contact admin with inline facts and observations visible from one page.
    '''
    list_display = [
        'first_name',
        'last_name',
        'email',
        'user',
        'relationship_trend',
        'connection_strength',
    ]
    search_fields = ['first_name', 'last_name', 'email']
    list_filter = ['relationship_trend']
    readonly_fields = [
        'interaction_frequency_score',
        'relationship_trend',
        'interaction_diversity_score',
        'sentiment_profile',
        'connection_strength',
    ]
    inlines = [FactInline, ObservationInline]

@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ['contact', 'marker', 'created_timestamp', 'is_active']
    list_filter = ['is_active', 'marker']
    search_fields = ['contact__first_name', 'contact__last_name', 'body']
