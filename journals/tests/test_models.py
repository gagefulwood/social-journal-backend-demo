from django.test import TestCase

from journals.models import Exercise, ExerciseStep, JournalBase, Log, Reflection
from lookups.models import EntryTag

from .factories import (
    EventFactory,
    LogFactory,
    ReflectionFactory,
    UserFactory,
)


class JournalModelTests(TestCase):
    def test_journal_base_is_abstract(self):
        self.assertTrue(JournalBase._meta.abstract)

    def test_concrete_db_table_names(self):
        self.assertEqual(Log._meta.db_table, 'logs')
        self.assertEqual(Reflection._meta.db_table, 'reflections')
        self.assertEqual(Exercise._meta.db_table, 'exercises')
        self.assertEqual(ExerciseStep._meta.db_table, 'exercise_steps')

    def test_log_defaults_and_str(self):
        log = LogFactory(title='Dinner notes')

        self.assertEqual(log.subtype, 'standard')
        self.assertEqual(log.data, {})
        self.assertEqual(str(log), 'Dinner notes')

    def test_reflection_defaults_and_str(self):
        reflection = ReflectionFactory(title='Dinner reflection', subtype='standard')

        self.assertEqual(reflection.subtype, 'standard')
        self.assertEqual(str(reflection), 'Dinner reflection')

    def test_log_tags_accept_entry_tag_rows(self):
        user = UserFactory()
        event = EventFactory(user=user)
        log = LogFactory(user=user, event=event)
        tag = EntryTag.objects.create(user=user, tag_name='Important')

        log.tags.add(tag)

        self.assertEqual(list(log.tags.all()), [tag])
        self.assertEqual(list(tag.logs.all()), [log])


class JournalManagerTests(TestCase):
    def test_for_user_scopes_each_kind_to_requesting_user(self):
        user = UserFactory()
        other_user = UserFactory()
        log = LogFactory(user=user)
        reflection = ReflectionFactory(user=user)
        LogFactory(user=other_user)
        ReflectionFactory(user=other_user)

        self.assertEqual(list(Log.objects.for_user(user)), [log])
        self.assertEqual(list(Reflection.objects.for_user(user)), [reflection])
