from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.tests.factories import UserFactory
from lookups.models import EntryTag


class EntryTagModelTests(TestCase):
    def test_str_returns_tag_name(self):
        tag = EntryTag.objects.create(tag_name="Important", is_system_default=True)

        self.assertEqual(str(tag), "Important")

    def test_db_table_is_entry_tags(self):
        self.assertEqual(EntryTag._meta.db_table, "entry_tags")

    def test_for_user_returns_system_defaults_and_user_rows(self):
        user = UserFactory()
        other_user = UserFactory()
        system_tag = EntryTag.objects.create(
            tag_name="Important",
            is_system_default=True,
        )
        user_tag = EntryTag.objects.create(
            user=user,
            tag_name="Personal",
        )
        other_tag = EntryTag.objects.create(
            user=other_user,
            tag_name="Other",
        )

        tags = EntryTag.objects.for_user(user)
        tag_ids = {tag.id for tag in tags}

        self.assertIn(system_tag.id, tag_ids)
        self.assertIn(user_tag.id, tag_ids)
        self.assertNotIn(other_tag.id, tag_ids)
        self.assertTrue(all(tag.is_system_default or tag.user == user for tag in tags))


class EntryTagViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_visible_entry_tags(self):
        system_tag = EntryTag.objects.create(
            tag_name="Important",
            is_system_default=True,
        )
        user_tag = EntryTag.objects.create(
            user=self.user,
            tag_name="Personal",
        )
        other_tag = EntryTag.objects.create(
            user=self.other_user,
            tag_name="Other",
        )

        response = self.client.get(reverse("entry-tag-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tag_ids = {tag["id"] for tag in response.data}
        self.assertIn(system_tag.id, tag_ids)
        self.assertIn(user_tag.id, tag_ids)
        self.assertNotIn(other_tag.id, tag_ids)

    def test_journal_tags_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("journal-tag-list")

    def test_journal_tags_path_is_removed(self):
        response = self.client.get("/api/lookups/journal-tags/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
