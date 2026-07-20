import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def mark_existing_assets_ready(apps, schema_editor):
    MediaAsset = apps.get_model('media', 'MediaAsset')
    MediaAsset.objects.update(
        status='ready',
        verification_method='legacy_unverified',
        failure_code='',
    )


def unmark_existing_assets(apps, schema_editor):
    MediaAsset = apps.get_model('media', 'MediaAsset')
    MediaAsset.objects.filter(
        verification_method='legacy_unverified',
    ).update(verification_method='')


class Migration(migrations.Migration):

    dependencies = [
        ('media', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='mediaasset',
            name='claimed_content_type',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='deleted_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='detected_content_type',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='duration_ms',
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='failure_code',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='height',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='pixel_count',
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('processing', 'Processing'),
                    ('ready', 'Ready'),
                    ('failed', 'Failed'),
                    ('aborted', 'Aborted'),
                ],
                default='ready',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='verification_method',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='verified_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mediaasset',
            name='width',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='mediaasset',
            index=models.Index(
                fields=['user', 'status', '-created_timestamp'],
                name='media_owner_status_created_idx',
            ),
        ),
        migrations.RunPython(
            mark_existing_assets_ready,
            unmark_existing_assets,
        ),
        migrations.CreateModel(
            name='MediaUploadSession',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    'idempotency_key_hash',
                    models.CharField(max_length=64),
                ),
                (
                    'original_filename',
                    models.CharField(blank=True, max_length=255),
                ),
                (
                    'claimed_content_type',
                    models.CharField(blank=True, max_length=255),
                ),
                (
                    'expected_bytes',
                    models.PositiveBigIntegerField(blank=True, null=True),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending'),
                            ('verifying', 'Verifying'),
                            ('ready', 'Ready'),
                            ('failed', 'Failed'),
                            ('aborted', 'Aborted'),
                        ],
                        default='pending',
                        max_length=20,
                    ),
                ),
                (
                    'failure_code',
                    models.CharField(blank=True, max_length=80),
                ),
                ('expires_at', models.DateTimeField()),
                ('created_timestamp', models.DateTimeField(auto_now_add=True)),
                ('updated_timestamp', models.DateTimeField(auto_now=True)),
                (
                    'media_asset',
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='upload_session',
                        to='media.mediaasset',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='media_upload_sessions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'db_table': 'media_upload_sessions',
                'ordering': ['-created_timestamp'],
                'indexes': [
                    models.Index(
                        fields=['user', 'status', 'expires_at'],
                        name='media_up_owner_status_exp_idx',
                    ),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('user', 'idempotency_key_hash'),
                        name='uniq_owner_media_idem_key',
                    ),
                ],
            },
        ),
    ]
