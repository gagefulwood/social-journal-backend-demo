import uuid

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
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_ABORTED = 'aborted'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_READY, 'Ready'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_ABORTED, 'Aborted'),
    ]

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
    claimed_content_type = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=255)
    detected_content_type = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_READY,
    )
    verification_method = models.CharField(max_length=50, blank=True)
    failure_code = models.CharField(max_length=80, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    pixel_count = models.PositiveBigIntegerField(null=True, blank=True)
    duration_ms = models.PositiveBigIntegerField(null=True, blank=True)
    verified_timestamp = models.DateTimeField(null=True, blank=True)
    alt_text = models.CharField(max_length=255, blank=True)
    caption = models.TextField(blank=True)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)
    deleted_timestamp = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    objects = MediaAssetManager()

    class Meta:
        db_table = 'media_assets'
        ordering = ['-created_timestamp']
        indexes = [
            models.Index(
                fields=['user', 'status', '-created_timestamp'],
                name='media_owner_status_created_idx',
            ),
        ]

    def __str__(self):
        return self.original_filename

    @property
    def is_referenced(self):
        for relation in self._meta.related_objects:
            accessor = relation.get_accessor_name()
            if not accessor or accessor == 'upload_session':
                continue
            try:
                related = getattr(self, accessor)
            except relation.related_model.DoesNotExist:
                continue
            if hasattr(related, 'exists'):
                if related.exists():
                    return True
            elif related is not None:
                return True
        return False


class MediaUploadSessionManager(models.Manager):
    def for_user(self, user):
        return self.get_queryset().filter(user=user)


class MediaUploadSession(models.Model):
    '''
    Owner-scoped record for an HTTP upload attempt.

    The caller's idempotency key is stored only as a SHA-256 digest. Uploads are
    currently request-bound; the model deliberately does not imply resumable or
    provider-multipart support.
    '''

    STATUS_PENDING = 'pending'
    STATUS_VERIFYING = 'verifying'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_ABORTED = 'aborted'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_VERIFYING, 'Verifying'),
        (STATUS_READY, 'Ready'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_ABORTED, 'Aborted'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='media_upload_sessions',
    )
    idempotency_key_hash = models.CharField(max_length=64)
    original_filename = models.CharField(max_length=255, blank=True)
    claimed_content_type = models.CharField(max_length=255, blank=True)
    expected_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    failure_code = models.CharField(max_length=80, blank=True)
    media_asset = models.OneToOneField(
        MediaAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upload_session',
    )
    expires_at = models.DateTimeField()
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    objects = MediaUploadSessionManager()

    class Meta:
        db_table = 'media_upload_sessions'
        ordering = ['-created_timestamp']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'idempotency_key_hash'],
                name='uniq_owner_media_idem_key',
            ),
        ]
        indexes = [
            models.Index(
                fields=['user', 'status', 'expires_at'],
                name='media_up_owner_status_exp_idx',
            ),
        ]
