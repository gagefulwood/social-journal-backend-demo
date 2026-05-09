import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from contacts.tests.factories import UserFactory
from lookups.models import MediaType
from media.serializers import MediaAssetSerializer


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
        upload = SimpleUploadedFile(
            "avatar.png",
            b"image-bytes",
            content_type="image/png",
        )
        serializer = MediaAssetSerializer(data={"file": upload, "alt_text": "Avatar"})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        asset = serializer.save(user=self.user)

        self.assertEqual(asset.original_filename, "avatar.png")
        self.assertEqual(asset.content_type, "image/png")
        self.assertEqual(asset.file_size, len(b"image-bytes"))
        self.assertEqual(asset.media_type, self.image_type)
        self.assertEqual(asset.alt_text, "Avatar")
        self.assertTrue(asset.file.name.startswith("media/"))

    def test_url_is_read_only(self):
        upload = SimpleUploadedFile(
            "avatar.png",
            b"image-bytes",
            content_type="image/png",
        )
        serializer = MediaAssetSerializer(
            data={"file": upload, "url": "https://example.com/ignored.png"}
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        asset = serializer.save(user=self.user)

        self.assertNotEqual(
            MediaAssetSerializer(asset).data["url"],
            "https://example.com/ignored.png",
        )
