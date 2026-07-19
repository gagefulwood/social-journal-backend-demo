from django.contrib import admin

from .models import Log, Reflection


@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'format',
        'status',
        'event',
        'primary_contact',
        'occurred_at',
        'updated_timestamp',
    )
    list_filter = ('format', 'status', 'created_timestamp')
    search_fields = ('title',)


@admin.register(Reflection)
class ReflectionAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'format',
        'status',
        'event',
        'primary_contact',
        'occurred_at',
        'updated_timestamp',
    )
    list_filter = ('format', 'status', 'created_timestamp')
    search_fields = ('title',)
