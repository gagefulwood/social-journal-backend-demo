from django.contrib import admin
from .models import SocialGroup, GroupMember

# Register your models here.
@admin.register(SocialGroup)
class SocialGroupAdmin(admin.ModelAdmin):
    list_display = ("group_name", "user", "activity_score", "created_at")
    search_fields = ("group_name", "user__username")
    list_filter = ("created_at",)


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ("group", "contact")
    search_fields = ("group__group_name", "contact__id")