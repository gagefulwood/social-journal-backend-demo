from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from media.models import MediaAsset, MediaUploadSession
from media.services import asset_is_referenced, delete_asset_bytes


class Command(BaseCommand):
    help = (
        'Preview or apply idempotent cleanup of expired upload sessions and '
        'unreferenced media bytes.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply cleanup. The default is a read-only preview.',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        deleted_cutoff = now - timedelta(
            seconds=settings.MEDIA_DELETED_ASSET_RETENTION_SECONDS
        )
        unattached_cutoff = now - timedelta(
            seconds=settings.MEDIA_UNATTACHED_ASSET_RETENTION_SECONDS
        )
        terminal_session_cutoff = now - timedelta(
            seconds=settings.MEDIA_UPLOAD_SESSION_RETENTION_SECONDS
        )
        apply_cleanup = options['apply']

        expired_sessions = MediaUploadSession.objects.filter(
            status__in=[
                MediaUploadSession.STATUS_PENDING,
                MediaUploadSession.STATUS_VERIFYING,
            ],
            expires_at__lte=now,
        )
        deleted_assets = MediaAsset.objects.filter(
            is_active=False,
        ).filter(
            Q(deleted_timestamp__lte=deleted_cutoff)
            | Q(
                deleted_timestamp__isnull=True,
                updated_timestamp__lte=deleted_cutoff,
            )
        )
        terminal_sessions = MediaUploadSession.objects.filter(
            status__in=[
                MediaUploadSession.STATUS_READY,
                MediaUploadSession.STATUS_FAILED,
                MediaUploadSession.STATUS_ABORTED,
            ],
            updated_timestamp__lte=terminal_session_cutoff,
        )
        unattached_assets = MediaAsset.objects.filter(
            is_active=True,
            status=MediaAsset.STATUS_READY,
            created_timestamp__lte=unattached_cutoff,
        )

        preview = {
            'expired_sessions': expired_sessions.count(),
            'terminal_sessions': terminal_sessions.count(),
            'deleted_asset_candidates': deleted_assets.count(),
            'unattached_asset_candidates': unattached_assets.count(),
        }
        if not apply_cleanup:
            self.stdout.write(
                'Would clean '
                f'{preview["expired_sessions"]} expired sessions, '
                f'{preview["terminal_sessions"]} retained terminal sessions, '
                f'{preview["deleted_asset_candidates"]} deleted assets, and '
                f'{preview["unattached_asset_candidates"]} unattached assets.'
            )
            return

        expired_count = expired_sessions.update(
            status=MediaUploadSession.STATUS_ABORTED,
            failure_code='session_expired',
            updated_timestamp=now,
        )
        terminal_count = terminal_sessions.delete()[0]
        purged_deleted = self._purge_inactive(deleted_assets)
        purged_unattached = 0
        for asset_id in unattached_assets.values_list('id', flat=True).iterator():
            with transaction.atomic():
                asset = MediaAsset.objects.select_for_update().get(pk=asset_id)
                if not asset.is_active or asset_is_referenced(asset):
                    continue
                asset.is_active = False
                asset.deleted_timestamp = now
                asset.save(
                    update_fields=[
                        'is_active',
                        'deleted_timestamp',
                        'updated_timestamp',
                    ]
                )
            if delete_asset_bytes(asset):
                purged_unattached += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Cleaned {expired_count} expired sessions, '
                f'{terminal_count} retained terminal sessions, '
                f'{purged_deleted} deleted assets, and '
                f'{purged_unattached} unattached assets.'
            )
        )

    @staticmethod
    def _purge_inactive(queryset):
        purged = 0
        for asset_id in queryset.values_list('id', flat=True).iterator():
            asset = MediaAsset.objects.get(pk=asset_id)
            if delete_asset_bytes(asset):
                purged += 1
        return purged
