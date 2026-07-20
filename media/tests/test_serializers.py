import hashlib
import shutil
import tempfile
from urllib.parse import parse_qs, urlsplit

from django.test import TestCase, override_settings

from contacts.tests.factories import UserFactory
from lookups.models import MediaType
from media.serializers import MediaAssetSerializer
from media.signing import unsign_media_content

from .helpers import image_bytes, image_upload


class MediaAssetSerializerTests(TestCase):
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
        self.user = UserFactory()
        self.image_type = MediaType.objects.filter(name="IMAGE").first()
        if self.image_type is None:
            self.image_type = MediaType.objects.create(
                name="IMAGE",
                is_system_default=True,
            )

    def test_create_populates_upload_metadata_and_infers_media_type(self):
        expected_bytes = image_bytes()
        upload = image_upload()
        serializer = MediaAssetSerializer(data={"file": upload, "alt_text": "Avatar"})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        asset = serializer.save(user=self.user)

        self.assertEqual(asset.original_filename, "avatar.png")
        self.assertEqual(asset.content_type, "image/png")
        self.assertEqual(asset.claimed_content_type, "image/png")
        self.assertEqual(asset.detected_content_type, "image/png")
        self.assertEqual(asset.file_size, len(expected_bytes))
        self.assertEqual(asset.checksum, hashlib.sha256(expected_bytes).hexdigest())
        self.assertEqual(asset.status, asset.STATUS_READY)
        self.assertEqual(asset.verification_method, "pillow_decode")
        self.assertEqual((asset.width, asset.height, asset.pixel_count), (4, 3, 12))
        self.assertIsNotNone(asset.verified_timestamp)
        self.assertEqual(asset.media_type, self.image_type)
        self.assertEqual(asset.alt_text, "Avatar")
        self.assertTrue(asset.file.name.startswith("media/"))

    def test_url_is_read_only(self):
        upload = image_upload()
        serializer = MediaAssetSerializer(
            data={"file": upload, "url": "https://example.com/ignored.png"}
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        asset = serializer.save(user=self.user)

        data = MediaAssetSerializer(asset).data
        parsed = urlsplit(data["url"])
        self.assertEqual(parsed.path, f"/api/media/{asset.id}/content/")
        token = parse_qs(parsed.query)["token"][0]
        self.assertEqual(
            unsign_media_content(token),
            (self.user.id, asset.id),
        )
        self.assertEqual(data["content_url"], data["url"])
        self.assertNotIn("file", data)
        self.assertNotIn(asset.file.name, data["url"])

    def test_rejects_claimed_content_type_that_does_not_match_bytes(self):
        serializer = MediaAssetSerializer(
            data={"file": image_upload(content_type="video/mp4")}
        )

        self.assertFalse(serializer.is_valid())
        self.assertEqual(serializer.errors["file"][0].code, "content_type_mismatch")

    def test_rejects_trailing_polyglot_bytes(self):
        serializer = MediaAssetSerializer(
            data={"file": image_upload(trailing=b"<script>alert(1)</script>")}
        )

        self.assertFalse(serializer.is_valid())
        self.assertEqual(serializer.errors["file"][0].code, "image_trailing_data")

    def test_checksum_and_detected_metadata_are_read_only(self):
        serializer = MediaAssetSerializer(
            data={
                "file": image_upload(),
                "checksum": "caller-controlled",
                "content_type": "text/html",
                "detected_content_type": "text/html",
                "status": "ready",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        asset = serializer.save(user=self.user)
        self.assertNotEqual(asset.checksum, "caller-controlled")
        self.assertEqual(asset.content_type, "image/png")
        self.assertEqual(asset.detected_content_type, "image/png")
