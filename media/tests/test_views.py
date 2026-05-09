import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import UserFactory
from lookups.models import MediaType
from media.models import MediaAsset

from .factories import MediaAssetFactory


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

    def test_list_returns_paginated_assets_scoped_to_user(self):
        asset = MediaAssetFactory(user=self.user)
        MediaAssetFactory(user=self.other_user)

        response = self.client.get(reverse("media-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], asset.id)

    def test_create_upload_sets_user_and_metadata(self):
        upload = SimpleUploadedFile(
            "avatar.png",
            b"image-bytes",
            content_type="image/png",
        )

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
        self.assertEqual(asset.file_size, len(b"image-bytes"))
        self.assertEqual(asset.alt_text, "Avatar")

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

    def test_delete_soft_deletes_db_row_only(self):
        asset = MediaAssetFactory(user=self.user)
        file_name = asset.file.name

        response = self.client.delete(reverse("media-detail", args=[asset.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        asset.refresh_from_db()
        self.assertFalse(asset.is_active)
        self.assertEqual(asset.file.name, file_name)
        self.assertFalse(
            MediaAsset.objects.for_user(self.user).filter(id=asset.id).exists()
        )
