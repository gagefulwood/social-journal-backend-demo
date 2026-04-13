from django.contrib import admin
from .models import JournalEntry, Reflection, JournalTag

# Register your models here.
@admin.register(JournalTag)
class JournalTagAdmin(admin.ModelAdmin):
    list_display = ("tag_name", "user", "is_system_default")
    search_fields = ("tag_name",)

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "event", "entry_timestamp", "is_immutable")
    list_filter = ("is_immutable", "entry_timestamp", "mood")
    search_fields = ("title", "body")
    filter_horizontal = ("tags",)

@admin.register(Reflection)
class ReflectionAdmin(admin.ModelAdmin):
    list_display = ("journal_entry", "created_timestamp")
    search_fields = ("body",)