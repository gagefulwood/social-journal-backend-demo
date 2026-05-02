from django.contrib import admin

from .models import Exercise, ExerciseStep, Log, Reflection


@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display = ('title', 'event', 'created_timestamp', 'updated_timestamp')
    list_filter = ('subtype', 'mood', 'created_timestamp')
    search_fields = ('title', 'body')
    filter_horizontal = ('tags',)


@admin.register(Reflection)
class ReflectionAdmin(admin.ModelAdmin):
    list_display = ('event', 'subtype', 'clarity_check', 'created_timestamp')
    list_filter = ('subtype', 'created_timestamp')
    search_fields = ('clarity_check',)


class ExerciseStepInline(admin.TabularInline):
    model = ExerciseStep
    extra = 0


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = (
        'event',
        'subtype',
        'pre_measurement',
        'post_measurement',
        'created_timestamp',
    )
    list_filter = ('subtype', 'created_timestamp')
    inlines = [ExerciseStepInline]
