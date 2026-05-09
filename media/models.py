from django.conf import settings
from django.db import models


class MediaAssetManager(models.Manager):
    '''
    Custom manager for user-owned media assets.
    for_user() returns only active media assets owned by the requesting user.
    '''
    def for_user(self, user):
        return self.get_queryset().filter(user=user, is_active=True)


class MediaAsset(models.Model):
    '''
    User-owned uploaded file stored through the configured media storage backend.
    S3-compatible providers use private objects and short-lived presigned URLs.
    '''
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='media_assets',
    )
    file = models.FileField(upload_to='media/%Y/%m/%d/')
    media_type = models.ForeignKey(
        'lookups.MediaType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assets',
    )
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=128, blank=True)
    alt_text = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    objects = MediaAssetManager()

    class Meta:
        db_table = 'media_assets'
        ordering = ['-created_timestamp']

    def __str__(self):
        return self.original_filename
