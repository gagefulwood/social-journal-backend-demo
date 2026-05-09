from django.contrib import admin

from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = [
        'original_filename',
        'user',
        'media_type',
        'content_type',
        'file_size',
        'is_active',
        'created_timestamp',
    ]
    list_filter = ['media_type', 'content_type', 'is_active']
    search_fields = ['original_filename', 'user__email', 'caption', 'alt_text']
