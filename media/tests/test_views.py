import hashlib
import os
import shutil
import tempfile
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import signing
from django.core.files.uploadhandler import StopUpload
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from events.models import Event, EventMedia
from contacts.tests.factories import UserFactory
from lookups.models import MediaType
from media.models import MediaAsset, MediaUploadSession
from media.signing import sign_media_content
from media.upload_handlers import CappedMediaUploadHandler

from .factories import MediaAssetFactory
from .helpers import image_bytes, image_upload


class MediaAssetViewSetTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()
        cls.override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)
        if not MediaType.objects.filter(name="IMAGE").exists():
            MediaType.objects.create(name="IMAGE", is_system_default=True)

    def _content_url(self, asset):
        return (
            f'{reverse("media-content", args=[asset.id])}?'
            f'{urlencode({"token": sign_media_content(asset)})}'
        )

    def test_list_returns_paginated_assets_scoped_to_user(self):
        asset = MediaAssetFactory(user=self.user)
        MediaAssetFactory(user=self.other_user)

        response = self.client.get(reverse("media-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], asset.id)

    def test_create_upload_sets_user_and_metadata(self):
        expected_bytes = image_bytes()
        upload = image_upload()

        response = self.client.post(
            reverse("media-list"),
            {"file": upload, "alt_text": "Avatar"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        asset = MediaAsset.objects.get(id=response.data["id"])
        self.assertEqual(asset.user, self.user)
        self.assertEqual(asset.original_filename, "avatar.png")
        self.assertEqual(asset.content_type, "image/png")
        self.assertEqual(asset.detected_content_type, "image/png")
        self.assertEqual(asset.file_size, len(expected_bytes))
        self.assertEqual(asset.checksum, hashlib.sha256(expected_bytes).hexdigest())
        self.assertEqual(asset.status, MediaAsset.STATUS_READY)
        self.assertEqual(asset.alt_text, "Avatar")
        self.assertNotIn("file", response.data)
        parsed_content_url = urlsplit(response.data["content_url"])
        self.assertEqual(parsed_content_url.path, f"/api/media/{asset.id}/content/")
        self.assertTrue(parsed_content_url.query.startswith("token="))
        self.assertEqual(
            response.data["upload_session_status"],
            MediaUploadSession.STATUS_READY,
        )

    def test_retrieve_returns_404_for_other_users_asset(self):
        other_asset = MediaAssetFactory(user=self.other_user)

        response = self.client.get(reverse("media-detail", args=[other_asset.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_updates_metadata_for_owner(self):
        asset = MediaAssetFactory(user=self.user, caption="")

        response = self.client.patch(
            reverse("media-detail", args=[asset.id]),
            {"caption": "Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        asset.refresh_from_db()
        self.assertEqual(asset.caption, "Updated")

    def test_patch_cannot_relabel_server_inferred_media_type(self):
        asset = MediaAssetFactory(user=self.user)
        audio_type = MediaType.objects.create(name="AUDIO", is_system_default=True)

        response = self.client.patch(
            reverse("media-detail", args=[asset.id]),
            {"media_type_id": audio_type.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        asset.refresh_from_db()
        self.assertNotEqual(asset.media_type_id, audio_type.id)

    def test_delete_marks_unreferenced_asset_for_recoverable_cleanup(self):
        asset = MediaAssetFactory(user=self.user)
        file_name = asset.file.name

        response = self.client.delete(reverse("media-detail", args=[asset.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        asset.refresh_from_db()
        self.assertFalse(asset.is_active)
        self.assertIsNotNone(asset.deleted_timestamp)
        self.assertEqual(asset.file.name, file_name)
        self.assertFalse(
            MediaAsset.objects.for_user(self.user).filter(id=asset.id).exists()
        )

    def test_delete_refuses_asset_referenced_by_event_media(self):
        asset = MediaAssetFactory(user=self.user)
        event = Event.objects.create(
            user=self.user,
            title="Referenced event",
            event_timestamp=timezone.now(),
        )
        EventMedia.objects.create(
            event=event,
            media_asset=asset,
            display_order=0,
            alt_text="Event photo",
        )

        response = self.client.delete(reverse("media-detail", args=[asset.id]))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "media_in_use")
        asset.refresh_from_db()
        self.assertTrue(asset.is_active)

    def test_content_streams_owner_file_with_range_head_and_nosniff(self):
        payload = image_bytes()
        created = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
        )
        content_url = created.data["content_url"]

        full = self.client.get(content_url)
        ranged = self.client.get(content_url, HTTP_RANGE="bytes=0-7")
        head = self.client.head(content_url)

        self.assertEqual(full.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(full.streaming_content), payload)
        self.assertEqual(full["X-Content-Type-Options"], "nosniff")
        self.assertEqual(full["Accept-Ranges"], "bytes")
        self.assertEqual(full["Cache-Control"], "private, no-store")
        self.assertEqual(ranged.status_code, status.HTTP_206_PARTIAL_CONTENT)
        self.assertEqual(b"".join(ranged.streaming_content), payload[:8])
        self.assertEqual(ranged["Content-Range"], f"bytes 0-7/{len(payload)}")
        self.assertEqual(head.status_code, status.HTTP_200_OK)
        self.assertEqual(int(head["Content-Length"]), len(payload))
        self.assertEqual(head.content, b"")

    def test_content_returns_416_for_invalid_or_multiple_range(self):
        created = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
        )
        content_url = created.data["content_url"]

        response = self.client.get(
            content_url,
            HTTP_RANGE="bytes=0-1,4-5",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
        )
        self.assertIn("bytes */", response["Content-Range"])

    def test_signed_content_url_authorizes_native_request_without_cookie(self):
        created = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
        )
        self.client.force_authenticate(user=None)

        response = self.client.get(
            created.data["content_url"],
            HTTP_RANGE="bytes=0-7",
        )

        self.assertEqual(response.status_code, status.HTTP_206_PARTIAL_CONTENT)
        self.assertEqual(len(b"".join(response.streaming_content)), 8)

    @patch("media.services.ffprobe_available", return_value=False)
    def test_verified_audio_delivery_remains_playable_if_probe_later_unavailable(
        self,
        _available,
    ):
        upload = image_upload()
        asset = MediaAsset.objects.create(
            user=self.user,
            file=upload,
            original_filename="verified.wav",
            content_type="audio/wav",
            detected_content_type="audio/wav",
            file_size=upload.size,
            status=MediaAsset.STATUS_READY,
            verification_method="ffprobe",
        )

        response = self.client.get(self._content_url(asset))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "audio/wav")

    @patch("media.services.ffprobe_available", return_value=True)
    def test_legacy_unverified_audio_is_not_served_inline(self, _available):
        upload = image_upload()
        asset = MediaAsset.objects.create(
            user=self.user,
            file=upload,
            original_filename="legacy.wav",
            content_type="audio/wav",
            detected_content_type="audio/wav",
            file_size=upload.size,
            status=MediaAsset.STATUS_READY,
            verification_method="legacy_unverified",
        )

        response = self.client.get(self._content_url(asset))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))

    @patch("media.views.unsign_media_content", side_effect=signing.SignatureExpired)
    def test_expired_signed_content_url_fails_with_refreshable_code(self, _unsign):
        asset = MediaAssetFactory(user=self.user)

        response = self.client.get(self._content_url(asset))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "signed_media_url_expired")

    def test_content_is_owner_scoped_and_missing_bytes_are_not_redirected(self):
        other_asset = MediaAssetFactory(user=self.other_user)
        missing_asset = MediaAssetFactory(user=self.user)

        unsigned = self.client.get(
            reverse("media-content", args=[missing_asset.id])
        )
        tampered = self.client.get(
            f'{reverse("media-content", args=[other_asset.id])}?'
            f'{urlencode({"token": sign_media_content(missing_asset)})}'
        )
        missing = self.client.get(self._content_url(missing_asset))

        self.assertEqual(unsigned.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(tampered.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(missing.data["code"], "media_bytes_missing")

    def test_idempotency_key_replays_completed_upload(self):
        first = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="stable-upload-key",
        )
        second = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="stable-upload-key",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(second["Idempotency-Replayed"], "true")
        self.assertEqual(MediaAsset.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            MediaUploadSession.objects.filter(user=self.user).count(),
            1,
        )

    def test_deterministic_validation_failure_replays_without_new_upload(self):
        first = self.client.post(
            reverse("media-list"),
            {"file": image_upload(trailing=b"trailing")},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="invalid-upload-key",
        )
        second = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="invalid-upload-key",
        )

        self.assertEqual(first.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(first.data["code"], "image_trailing_data")
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "image_trailing_data")
        self.assertFalse(MediaAsset.objects.filter(user=self.user).exists())

    def test_cancelled_session_can_retry_with_same_key_and_identity(self):
        key = "retryable-upload-key"
        session = MediaUploadSession.objects.create(
            user=self.user,
            idempotency_key_hash=hashlib.sha256(key.encode()).hexdigest(),
            status=MediaUploadSession.STATUS_ABORTED,
            failure_code="cancelled",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY=key,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["upload_session_id"], str(session.id))
        self.assertEqual(response["Upload-Session-Retried"], "true")
        session.refresh_from_db()
        self.assertEqual(session.status, MediaUploadSession.STATUS_READY)

    def test_probe_timeout_session_can_retry_with_same_key(self):
        key = "probe-timeout-retry-key"
        session = MediaUploadSession.objects.create(
            user=self.user,
            idempotency_key_hash=hashlib.sha256(key.encode()).hexdigest(),
            status=MediaUploadSession.STATUS_FAILED,
            failure_code="media_probe_timeout",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY=key,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["upload_session_id"], str(session.id))
        self.assertEqual(response["Upload-Session-Retried"], "true")

    def test_cancel_by_key_tombstone_blocks_racing_upload(self):
        key = "cancel-before-upload-key"

        cancelled = self.client.delete(
            reverse("media-upload-cancel"),
            HTTP_IDEMPOTENCY_KEY=key,
        )
        upload = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY=key,
        )

        self.assertEqual(cancelled.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(upload.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(upload.data["code"], "cancellation_requested")
        self.assertFalse(MediaAsset.objects.filter(user=self.user).exists())

    def test_page_exit_beacon_can_cancel_by_form_body(self):
        key = "page-exit-cancel-key"

        response = self.client.post(
            reverse("media-upload-cancel"),
            {"idempotency_key": key},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        session = MediaUploadSession.objects.get(user=self.user)
        self.assertEqual(
            session.idempotency_key_hash,
            hashlib.sha256(key.encode()).hexdigest(),
        )
        self.assertEqual(session.status, MediaUploadSession.STATUS_ABORTED)

    def test_cancel_by_key_soft_deletes_completed_unattached_upload(self):
        key = "cancel-completed-upload-key"
        upload = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY=key,
        )

        cancelled = self.client.delete(
            reverse("media-upload-cancel"),
            HTTP_IDEMPOTENCY_KEY=key,
        )

        self.assertEqual(upload.status_code, status.HTTP_201_CREATED)
        self.assertEqual(cancelled.status_code, status.HTTP_204_NO_CONTENT)
        asset = MediaAsset.objects.get(pk=upload.data["id"])
        self.assertFalse(asset.is_active)
        self.assertIsNotNone(asset.deleted_timestamp)

    @override_settings(MEDIA_UPLOAD_REQUEST_MAX_BYTES=8)
    def test_declared_oversized_request_is_rejected_before_file_parse(self):
        response = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="oversized-request-key",
            HTTP_CONTENT_LENGTH="1024",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
        self.assertEqual(response.data["code"], "upload_request_too_large")
        self.assertFalse(MediaAsset.objects.filter(user=self.user).exists())

    def test_streaming_handler_stops_unknown_length_upload_at_cap(self):
        request = SimpleNamespace()
        handler = CappedMediaUploadHandler(request, maximum_bytes=8)

        self.assertEqual(handler.receive_data_chunk(b"12345", 0), b"12345")
        with self.assertRaises(StopUpload):
            handler.receive_data_chunk(b"6789", 5)

        self.assertTrue(request._media_upload_limit_exceeded)

    def test_soft_deleted_retained_bytes_continue_to_consume_quota(self):
        payload_size = len(image_bytes())
        with self.settings(MEDIA_OWNER_STORAGE_QUOTA_BYTES=payload_size + 1):
            first = self.client.post(
                reverse("media-list"),
                {"file": image_upload()},
                format="multipart",
            )
            self.client.delete(
                reverse("media-detail", args=[first.data["id"]]),
            )
            second = self.client.post(
                reverse("media-list"),
                {"file": image_upload()},
                format="multipart",
            )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "owner_storage_quota_exceeded")

    @override_settings(MEDIA_MAX_CONCURRENT_UPLOADS=1)
    def test_concurrent_upload_limit_is_exposed_as_a_clear_error(self):
        MediaUploadSession.objects.create(
            user=self.user,
            idempotency_key_hash="a" * 64,
            status=MediaUploadSession.STATUS_VERIFYING,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse("media-list"),
            {"file": image_upload()},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="second-key",
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["code"], "concurrent_upload_limit_reached")

    def test_capabilities_report_enforced_and_deferred_features_honestly(self):
        response = self.client.get(reverse("media-capabilities"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("image/png", response.data["mime_types"]["image"])
        self.assertEqual(response.data["mime_types"]["video"], ())
        self.assertEqual(response.data["mime_types"]["audio"], ())
        self.assertTrue(response.data["verification"]["actual_bytes_verified"])
        self.assertTrue(response.data["delivery"]["range_requests"])
        self.assertTrue(response.data["delivery"]["signed_content_urls"])
        self.assertEqual(
            response.data["delivery"]["signed_url_expiry_seconds"],
            settings.MEDIA_CONTENT_URL_EXPIRY_SECONDS,
        )
        self.assertEqual(
            response.data["limits"]["video_max_duration_seconds"],
            settings.MEDIA_VIDEO_MAX_DURATION_SECONDS,
        )
        self.assertEqual(
            response.data["limits"]["video_max_width"],
            settings.MEDIA_VIDEO_MAX_WIDTH,
        )
        self.assertEqual(
            response.data["limits"]["video_max_height"],
            settings.MEDIA_VIDEO_MAX_HEIGHT,
        )
        self.assertEqual(
            response.data["limits"]["audio_max_duration_seconds"],
            settings.MEDIA_AUDIO_MAX_DURATION_SECONDS,
        )
        self.assertFalse(response.data["verification"]["ffprobe"])
        self.assertFalse(response.data["processing"]["transcoding"])
        self.assertFalse(response.data["upload"]["resumable_upload_supported"])

    def test_upload_session_detail_is_owner_scoped(self):
        session = MediaUploadSession.objects.create(
            user=self.other_user,
            idempotency_key_hash="b" * 64,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(
            reverse("media-upload-session-detail", args=[session.id])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_db_failure_does_not_leave_storage_orphan(self):
        before = {
            os.path.join(root, filename)
            for root, _, filenames in os.walk(self.media_root)
            for filename in filenames
        }
        with patch.object(
            MediaAsset,
            "_do_insert",
            side_effect=IntegrityError("simulated insert failure"),
        ):
            response = self.client.post(
                reverse("media-list"),
                {"file": image_upload()},
                format="multipart",
                HTTP_IDEMPOTENCY_KEY="storage-failure-key",
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["code"], "upload_storage_error")
        after = {
            os.path.join(root, filename)
            for root, _, filenames in os.walk(self.media_root)
            for filename in filenames
        }
        self.assertEqual(after, before)
