from django.contrib import admin
from .models import (
    Occupation,
    EducationLevel,
    ClosenessScore,
    Mood,
    ContextCategory,
    DetailCategoryTree,
    NoteMarker,
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


@admin.register(ClosenessScore)
class ClosenessScoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_system_default']


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


@admin.register(DetailCategoryTree)
class DetailCategoryTreeAdmin(admin.ModelAdmin):
    list_display  = ['name', 'parent', 'user', 'is_system_default']
    list_filter   = ['is_system_default']
    search_fields = ['name']


@admin.register(NoteMarker)
class NoteMarkerAdmin(admin.ModelAdmin):
    list_display  = ['name', 'color_hex', 'user', 'is_system_default']
    list_filter   = ['is_system_default']
    search_fields = ['name']


@admin.register(MediaType)
class MediaTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_system_default']