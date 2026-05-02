from datetime import timedelta

from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from journals.models import Exercise, Log, Reflection
from lookups.models import EntryTag, Mood

from .factories import (
    EventFactory,
    ExerciseFactory,
    LogFactory,
    ReflectionFactory,
    UserFactory,
)


class JournalKindViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.event = EventFactory(user=self.user)
        self.other_event = EventFactory(user=self.other_user)
        self.client.force_authenticate(user=self.user)

    def test_log_crud_and_filtering(self):
        mood = Mood.objects.create(user=self.user, name='Calm', emoji_icon='C')
        tag = EntryTag.objects.create(user=self.user, tag_name='Important')
        other_log = LogFactory(user=self.other_user)

        create_response = self.client.post(
            reverse('journal-log-list'),
            {
                'event': self.event.id,
                'title': 'Dinner',
                'body': 'Good conversation.',
                'mood_id': mood.id,
                'tag_ids': [tag.id],
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        log = Log.objects.get(id=create_response.data['id'])
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.event, self.event)
        self.assertEqual(log.mood, mood)
        self.assertEqual(list(log.tags.all()), [tag])

        list_response = self.client.get(
            reverse('journal-log-list'),
            {'mood': mood.id, 'tags': tag.id},
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data['count'], 1)
        self.assertEqual(list_response.data['results'][0]['id'], str(log.id))
        self.assertNotEqual(list_response.data['results'][0]['id'], str(other_log.id))

        patch_response = self.client.patch(
            reverse('journal-log-detail', args=[log.id]),
            {'body': 'Updated body.'},
            format='json',
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        log.refresh_from_db()
        self.assertEqual(log.body, 'Updated body.')

        delete_response = self.client.delete(reverse('journal-log-detail', args=[log.id]))
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Log.objects.filter(id=log.id).exists())

    def test_create_rejects_other_users_event(self):
        response = self.client.post(
            reverse('journal-reflection-list'),
            {
                'event': self.other_event.id,
                'clarity_check': 'Clear',
                'data': {'prompt': 'What happened?'},
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_same_kind_same_event_is_rejected(self):
        LogFactory(user=self.user, event=self.event)

        response = self.client.post(
            reverse('journal-log-list'),
            {
                'event': self.event.id,
                'title': 'Duplicate',
                'body': 'Duplicate body.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_event_can_have_one_of_each_kind(self):
        LogFactory(user=self.user, event=self.event)

        reflection_response = self.client.post(
            reverse('journal-reflection-list'),
            {
                'event': self.event.id,
                'clarity_check': 'Clear',
                'data': {'response': 'Something shifted.'},
            },
            format='json',
        )
        exercise_response = self.client.post(
            reverse('journal-exercise-list'),
            {
                'event': self.event.id,
                'pre_measurement': 2,
                'post_measurement': 5,
                'steps': [
                    {
                        'display_order': 1,
                        'prompt': 'Try a reframe.',
                        'response': 'I tried it.',
                    }
                ],
            },
            format='json',
        )

        self.assertEqual(reflection_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(exercise_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Reflection.objects.count(), 1)
        self.assertEqual(Exercise.objects.count(), 1)

    def test_old_journal_entry_routes_are_absent(self):
        with self.assertRaises(NoReverseMatch):
            reverse('journal-list')

        response = self.client.get('/api/journal/entries/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.get(f'/api/journals/entries/{self.event.id}/reflections/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class JournalFeedViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.event = EventFactory(user=self.user)
        self.client.force_authenticate(user=self.user)

    def test_combined_feed_returns_kind_discriminated_ordered_results(self):
        log = LogFactory(user=self.user, event=self.event, title='Old log')
        reflection = ReflectionFactory(user=self.user)
        exercise = ExerciseFactory(user=self.user)
        LogFactory(user=self.other_user)
        now = timezone.now()
        Log.objects.filter(pk=log.pk).update(created_timestamp=now - timedelta(days=2))
        Reflection.objects.filter(pk=reflection.pk).update(
            created_timestamp=now - timedelta(days=1)
        )
        Exercise.objects.filter(pk=exercise.pk).update(created_timestamp=now)

        response = self.client.get(reverse('journal-feed'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        kinds = [item['kind'] for item in response.data['results']]
        self.assertEqual(kinds, ['exercise', 'reflection', 'log'])

    def test_combined_feed_filters_by_kind_and_event(self):
        log = LogFactory(user=self.user, event=self.event)
        ReflectionFactory(user=self.user)

        response = self.client.get(
            reverse('journal-feed'),
            {'kind': 'log', 'event': self.event.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(log.id))
        self.assertEqual(response.data['results'][0]['kind'], 'log')

    def test_combined_feed_is_read_only(self):
        response = self.client.post(reverse('journal-feed'), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
