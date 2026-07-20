from django.contrib import admin

from .models import MediaAsset, MediaUploadSession


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = [
        'original_filename',
        'user',
        'media_type',
        'content_type',
        'status',
        'file_size',
        'is_active',
        'created_timestamp',
    ]
    list_filter = ['media_type', 'content_type', 'status', 'is_active']
    search_fields = ['original_filename', 'user__email', 'caption', 'alt_text']


@admin.register(MediaUploadSession)
class MediaUploadSessionAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'user',
        'status',
        'failure_code',
        'media_asset',
        'expires_at',
        'created_timestamp',
    ]
    list_filter = ['status', 'failure_code']
    search_fields = ['user__email', 'original_filename']
    readonly_fields = [
        'idempotency_key_hash',
        'created_timestamp',
        'updated_timestamp',
    ]
