from django.test import TestCase

from contacts.tests.factories import UserFactory
from media.models import MediaAsset

from .factories import MediaAssetFactory


class MediaAssetModelTests(TestCase):
    def test_str_returns_original_filename(self):
        asset = MediaAssetFactory(original_filename="avatar.png")

        self.assertEqual(str(asset), "avatar.png")

    def test_db_table_is_media_assets(self):
        self.assertEqual(MediaAsset._meta.db_table, "media_assets")

    def test_for_user_returns_active_assets_for_user_only(self):
        user = UserFactory()
        other_user = UserFactory()
        active_asset = MediaAssetFactory(user=user)
        MediaAssetFactory(user=user, is_active=False)
        MediaAssetFactory(user=other_user)

        assets = MediaAsset.objects.for_user(user)

        self.assertEqual(list(assets), [active_asset])
