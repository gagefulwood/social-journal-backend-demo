from django.test import TestCase

from contacts.tests.factories import UserFactory
from journal.models import JournalEntry
from lookups.models import EntryTag


class JournalEntryEntryTagTests(TestCase):
    def test_journal_entry_tags_accept_entry_tag_rows(self):
        user = UserFactory()
        entry = JournalEntry.objects.create(
            user=user,
            title="Dinner",
            body="Had dinner with a friend.",
        )
        tag = EntryTag.objects.create(user=user, tag_name="Important")

        entry.tags.add(tag)

        self.assertEqual(list(entry.tags.all()), [tag])

    def test_entry_tag_entries_reverse_accessor_returns_tagged_entries(self):
        user = UserFactory()
        entry = JournalEntry.objects.create(
            user=user,
            title="Dinner",
            body="Had dinner with a friend.",
        )
        tag = EntryTag.objects.create(user=user, tag_name="Important")

        entry.tags.add(tag)

        self.assertEqual(list(tag.entries.all()), [entry])
