from django.contrib import admin
from .models import (
    Occupation,
    EducationLevel,
    Relation,
    InteractionMode,
    Mood,
    ContextCategory,
    FactCategory,
    EntryTag,
    ObservationMarker,
    MediaType,
)


@admin.register(Occupation)
class OccupationAdmin(admin.ModelAdmin):
    list_display  = ['name', 'user', 'is_system_default']
    list_filter   = ['is_system_default']
    search_fields = ['name']


@admin.register(EducationLevel)
class EducationLevelAdmin(admin.ModelAdmin):
    list_display  = ['name', 'user', 'is_system_default']
    list_filter   = ['is_system_default']
    search_fields = ['name']


@admin.register(Relation)
class RelationAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_system_default']
    list_filter = ['is_system_default']
    search_fields = ['name']


@admin.register(InteractionMode)
class InteractionModeAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_system_default']
    list_filter = ['is_system_default']
    search_fields = ['name']


@admin.register(Mood)
class MoodAdmin(admin.ModelAdmin):
    list_display  = ['name', 'emoji_icon', 'user', 'is_system_default']
    list_filter   = ['is_system_default']
    search_fields = ['name']


@admin.register(ContextCategory)
class ContextCategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'color', 'user', 'is_system_default']
    list_filter   = ['is_system_default']
    search_fields = ['name']


@admin.register(FactCategory)
class FactCategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'parent', 'user', 'is_system_default']
    list_filter   = ['is_system_default']
    search_fields = ['name']

@admin.register(EntryTag)
class EntryTagAdmin(admin.ModelAdmin):
    list_display = ("tag_name", "user", "is_system_default")
    search_fields = ("tag_name",)


@admin.register(ObservationMarker)
class ObservationMarkerAdmin(admin.ModelAdmin):
    list_display  = ['name', 'color_hex', 'user', 'is_system_default']
    list_filter   = ['is_system_default']
    search_fields = ['name']


@admin.register(MediaType)
class MediaTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_system_default']
