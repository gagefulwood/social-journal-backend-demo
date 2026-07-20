import shutil
import tempfile
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from contacts.tests.factories import UserFactory
from events.models import Event, EventMedia
from media.models import MediaAsset, MediaUploadSession

from .helpers import image_upload


class MediaCleanupCommandTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()
        cls.override = override_settings(
            MEDIA_ROOT=cls.media_root,
            MEDIA_DELETED_ASSET_RETENTION_SECONDS=0,
            MEDIA_UNATTACHED_ASSET_RETENTION_SECONDS=0,
            MEDIA_UPLOAD_SESSION_RETENTION_SECONDS=60 * 60,
        )
        cls.override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = UserFactory()

    def asset(self, *, active=False):
        upload = image_upload()
        return MediaAsset.objects.create(
            user=self.user,
            file=upload,
            original_filename=upload.name,
            content_type="image/png",
            detected_content_type="image/png",
            file_size=upload.size,
            status=MediaAsset.STATUS_READY,
            is_active=active,
            deleted_timestamp=None if active else timezone.now(),
        )

    def test_default_is_read_only_preview(self):
        asset = self.asset()
        original_name = asset.file.name
        output = StringIO()

        call_command("cleanup_media", stdout=output)

        asset.refresh_from_db()
        self.assertEqual(asset.file.name, original_name)
        self.assertTrue(asset.file.storage.exists(original_name))
        self.assertIn("Would clean", output.getvalue())

    def test_apply_purges_inactive_unreferenced_bytes_idempotently(self):
        asset = self.asset()
        original_name = asset.file.name

        call_command("cleanup_media", apply=True, stdout=StringIO())
        call_command("cleanup_media", apply=True, stdout=StringIO())

        asset.refresh_from_db()
        self.assertEqual(asset.file.name, "")
        self.assertFalse(asset.file.storage.exists(original_name))

    def test_apply_purges_ready_unattached_asset_after_retention(self):
        asset = self.asset(active=True)
        original_name = asset.file.name

        call_command("cleanup_media", apply=True, stdout=StringIO())

        asset.refresh_from_db()
        self.assertFalse(asset.is_active)
        self.assertIsNotNone(asset.deleted_timestamp)
        self.assertEqual(asset.file.name, "")
        self.assertFalse(asset.file.storage.exists(original_name))

    def test_apply_never_purges_referenced_bytes(self):
        asset = self.asset()
        original_name = asset.file.name
        event = Event.objects.create(
            user=self.user,
            title="Referenced event",
            event_timestamp=timezone.now(),
        )
        EventMedia.objects.create(
            event=event,
            media_asset=asset,
            display_order=0,
            alt_text="Reference",
        )

        call_command("cleanup_media", apply=True, stdout=StringIO())

        asset.refresh_from_db()
        self.assertEqual(asset.file.name, original_name)
        self.assertTrue(asset.file.storage.exists(original_name))

    def test_apply_aborts_expired_request_bound_sessions(self):
        session = MediaUploadSession.objects.create(
            user=self.user,
            idempotency_key_hash="c" * 64,
            status=MediaUploadSession.STATUS_VERIFYING,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        call_command("cleanup_media", apply=True, stdout=StringIO())

        session.refresh_from_db()
        self.assertEqual(session.status, MediaUploadSession.STATUS_ABORTED)
        self.assertEqual(session.failure_code, "session_expired")

    def test_apply_purges_legacy_inactive_asset_without_deleted_timestamp(self):
        asset = self.asset()
        original_name = asset.file.name
        MediaAsset.objects.filter(pk=asset.pk).update(
            deleted_timestamp=None,
            updated_timestamp=timezone.now() - timedelta(days=1),
        )

        call_command("cleanup_media", apply=True, stdout=StringIO())

        asset.refresh_from_db()
        self.assertEqual(asset.file.name, "")
        self.assertFalse(asset.file.storage.exists(original_name))

    @override_settings(MEDIA_UPLOAD_SESSION_RETENTION_SECONDS=0)
    def test_apply_purges_terminal_sessions_after_retention(self):
        session = MediaUploadSession.objects.create(
            user=self.user,
            idempotency_key_hash="d" * 64,
            status=MediaUploadSession.STATUS_FAILED,
            failure_code="invalid_media",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        MediaUploadSession.objects.filter(pk=session.pk).update(
            updated_timestamp=timezone.now() - timedelta(days=1),
        )

        call_command("cleanup_media", apply=True, stdout=StringIO())

        self.assertFalse(MediaUploadSession.objects.filter(pk=session.pk).exists())
