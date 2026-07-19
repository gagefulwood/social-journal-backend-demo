from django.contrib import admin
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from contacts.models import Contact, Fact
from events.models import Event
from journals.models import (
    Exercise,
    Log,
    Reflection,
    SocialEnergyLogDetail,
)
from lookups.models import EmotionState, EpisodeCategory, FactCategory
from media.models import MediaAsset

from .factories import EventFactory, UserFactory


class TypedJournalApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.event = EventFactory(user=self.user)
        self.other_event = EventFactory(user=self.other_user)
        self.contact = Contact.objects.create(
            user=self.user,
            first_name='Alex',
            last_name='Rivera',
        )
        self.other_contact = Contact.objects.create(
            user=self.other_user,
            first_name='Private',
            last_name='Contact',
        )
        self.category = EpisodeCategory.objects.filter(
            code='thought_pattern',
            is_system_default=True,
        ).first()
        self.assertIsNotNone(self.category)
        self.client.force_authenticate(self.user)

    def _episode_payload(self):
        return {
            'format': 'episode',
            'title': 'Rumination spiral',
            'event_id': self.event.id,
            'occurred_at': timezone.now().isoformat(),
            'current_step': 'episode',
            'detail': {
                'category_id': self.category.id,
                'is_ongoing': True,
            },
        }

    def test_episode_revision_conflict_and_idempotent_completion(self):
        created = self.client.post(
            reverse('journal-log-list'),
            self._episode_payload(),
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data['status'], 'draft')
        self.assertEqual(created.data['revision'], 1)
        journal_id = created.data['id']

        patched = self.client.patch(
            reverse('journal-log-detail', args=[journal_id]),
            {
                'expected_revision': 1,
                'title': 'Updated rumination spiral',
            },
            format='json',
        )
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        self.assertEqual(patched.data['revision'], 2)

        stale = self.client.patch(
            reverse('journal-log-detail', args=[journal_id]),
            {'expected_revision': 1, 'title': 'Stale title'},
            format='json',
        )
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)

        completed = self.client.post(
            reverse('journal-log-complete', args=[journal_id]),
            {'expected_revision': 2},
            format='json',
        )
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertEqual(completed.data['status'], 'completed')
        self.assertEqual(completed.data['revision'], 3)
        self.assertEqual(completed.data['progress']['percent'], 100)
        completed_at = completed.data['completed_at']

        edited_completed = self.client.patch(
            reverse('journal-log-detail', args=[journal_id]),
            {
                'expected_revision': 3,
                'title': 'Edited after completion',
            },
            format='json',
        )
        self.assertEqual(
            edited_completed.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(edited_completed.data['status'], 'completed')
        self.assertEqual(edited_completed.data['completed_at'], completed_at)
        self.assertEqual(edited_completed.data['revision'], 4)

        stale_completed = self.client.patch(
            reverse('journal-log-detail', args=[journal_id]),
            {'expected_revision': 3, 'title': 'Stale completed edit'},
            format='json',
        )
        self.assertEqual(
            stale_completed.status_code,
            status.HTTP_409_CONFLICT,
        )

        repeated = self.client.post(
            reverse('journal-log-complete', args=[journal_id]),
            {'expected_revision': 2},
            format='json',
        )
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.data['revision'], 4)

    def test_completion_is_strict_but_event_and_contact_are_optional(self):
        created = self.client.post(
            reverse('journal-log-list'),
            {
                'format': 'social_energy',
                'title': 'Partial energy log',
                'detail': {'battery_effect': 'reduced'},
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        completed = self.client.post(
            reverse('journal-log-complete', args=[created.data['id']]),
            {'expected_revision': 1},
            format='json',
        )
        self.assertEqual(completed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('occurred_at', completed.data)
        self.assertIn('detail.mood_shift', completed.data)
        self.assertIn('detail.behavioral_effect', completed.data)
        self.assertIn('detail.group_size', completed.data)
        self.assertIn('detail.familiarity', completed.data)
        self.assertIn('detail.setting', completed.data)

        empty = self.client.post(
            reverse('journal-log-list'),
            {'format': 'episode'},
            format='json',
        )
        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sentiment_completion_keeps_connection_fields_optional(self):
        before = EmotionState.objects.get(
            code='positive',
            is_system_default=True,
        )
        after = EmotionState.objects.get(
            code='very_negative',
            is_system_default=True,
        )
        created = self.client.post(
            reverse('journal-log-list'),
            {
                'format': 'sentiment',
                'primary_contact_id': self.contact.id,
                'occurred_at': timezone.now().isoformat(),
                'detail': {
                    'before_state_id': before.id,
                    'after_state_id': after.id,
                },
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        completed = self.client.post(
            reverse('journal-log-complete', args=[created.data['id']]),
            {'expected_revision': 1},
            format='json',
        )
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertEqual(completed.data['status'], 'completed')
        self.assertEqual(completed.data['detail']['before_connection'], '')
        self.assertEqual(completed.data['detail']['after_connection'], '')
        self.assertEqual(completed.data['detail']['overall_exchange'], '')

        invalid_optional_enum = self.client.post(
            reverse('journal-log-list'),
            {
                'format': 'sentiment',
                'primary_contact_id': self.contact.id,
                'occurred_at': timezone.now().isoformat(),
                'detail': {
                    'before_state_id': before.id,
                    'after_state_id': after.id,
                    'overall_exchange': 'diagnosis',
                },
            },
            format='json',
        )
        self.assertEqual(
            invalid_optional_enum.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reflection_completion_requires_all_guided_prompts(self):
        occurred_at = timezone.now().isoformat()
        interaction = self.client.post(
            reverse('journal-reflection-list'),
            {
                'format': 'interaction',
                'primary_contact_id': self.contact.id,
                'occurred_at': occurred_at,
                'detail': {
                    'topic_or_activity': 'Planning the week',
                    'user_actions': 'I suggested two options.',
                    'contact_actions': 'They chose a time.',
                    'contact_response': 'They stayed engaged.',
                    'user_response': 'I relaxed.',
                },
            },
            format='json',
        )
        self.assertEqual(interaction.status_code, status.HTTP_201_CREATED)
        interaction_completion = self.client.post(
            reverse(
                'journal-reflection-complete',
                args=[interaction.data['id']],
            ),
            {'expected_revision': 1},
            format='json',
        )
        self.assertEqual(
            interaction_completion.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn('detail.feelings_now', interaction_completion.data)
        self.assertIn(
            'detail.important_to_understand',
            interaction_completion.data,
        )

        moment = self.client.post(
            reverse('journal-reflection-list'),
            {
                'format': 'moment',
                'detail': {
                    'focus_moment': 'A quiet pause',
                    'what_happened': 'We stopped and listened.',
                    'response': 'I stayed present.',
                    'stood_out': 'The quiet felt easy.',
                    'meaning_now': 'Comfort can be quiet.',
                },
            },
            format='json',
        )
        self.assertEqual(moment.status_code, status.HTTP_201_CREATED)
        moment_completion = self.client.post(
            reverse(
                'journal-reflection-complete',
                args=[moment.data['id']],
            ),
            {'expected_revision': 1},
            format='json',
        )
        self.assertEqual(
            moment_completion.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn('detail.noticed_around', moment_completion.data)
        self.assertIn('detail.remember', moment_completion.data)

        hurt = EmotionState.objects.get(
            code='hurt',
            is_system_default=True,
        )
        emotional = self.client.post(
            reverse('journal-reflection-list'),
            {
                'format': 'emotional',
                'detail': {
                    'emotion_ids': [hurt.id],
                    'situation': 'A plan changed without notice.',
                    'manifestations': [
                        {
                            'kind': 'thought',
                            'text': 'I need time to adjust.',
                            'display_order': 0,
                        }
                    ],
                    'communicating': 'I needed more notice.',
                },
            },
            format='json',
        )
        self.assertEqual(emotional.status_code, status.HTTP_201_CREATED)
        emotional_completion = self.client.post(
            reverse(
                'journal-reflection-complete',
                args=[emotional.data['id']],
            ),
            {'expected_revision': 1},
            format='json',
        )
        self.assertEqual(
            emotional_completion.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            'detail.connected_factors',
            emotional_completion.data,
        )
        self.assertIn(
            'detail.understanding_now',
            emotional_completion.data,
        )

    def test_cross_owner_context_is_rejected(self):
        payload = self._episode_payload()
        payload['event_id'] = self.other_event.id
        response = self.client.post(
            reverse('journal-log-list'),
            payload,
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('event_id', response.data)

        payload = self._episode_payload()
        payload['primary_contact_id'] = self.other_contact.id
        response = self.client.post(
            reverse('journal-log-list'),
            payload,
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('primary_contact_id', response.data)

    def test_reflection_carry_forward_is_atomic_and_idempotent(self):
        fact_category = FactCategory.objects.create(
            user=self.user,
            name='Preference',
        )
        created = self.client.post(
            reverse('journal-reflection-list'),
            {
                'format': 'free',
                'title': 'What I learned',
                'primary_contact_id': self.contact.id,
                'contact_ids': [self.contact.id],
                'detail': {'body': 'Asking for help invited connection.'},
                'carry_forward': {
                    'facts': [
                        {
                            'target_contact_id': self.contact.id,
                            'category_id': fact_category.id,
                            'label': 'Communication',
                            'detail_value': 'Values early updates',
                        }
                    ],
                    'observations': [],
                },
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        reflection_id = created.data['id']

        completed = self.client.post(
            reverse('journal-reflection-complete', args=[reflection_id]),
            {'expected_revision': 1},
            format='json',
        )
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        published_id = completed.data['carry_forward']['facts'][0][
            'published_fact_id'
        ]
        fact = Fact.objects.get(pk=published_id)
        self.assertEqual(str(fact.source_reflection_id), reflection_id)
        self.assertIsNotNone(fact.source_item_id)
        completed_at = completed.data['completed_at']
        fact_item = completed.data['carry_forward']['facts'][0]

        edited_completed = self.client.patch(
            reverse('journal-reflection-detail', args=[reflection_id]),
            {
                'expected_revision': 2,
                'title': 'What I learned, revised',
            },
            format='json',
        )
        self.assertEqual(
            edited_completed.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(edited_completed.data['status'], 'completed')
        self.assertEqual(edited_completed.data['completed_at'], completed_at)
        self.assertEqual(edited_completed.data['revision'], 3)

        unchanged_carry = self.client.patch(
            reverse('journal-reflection-detail', args=[reflection_id]),
            {
                'expected_revision': 3,
                'carry_forward': {
                    'facts': [
                        {
                            'id': fact_item['id'],
                            'target_contact_id': self.contact.id,
                            'category_id': fact_category.id,
                            'label': 'Communication',
                            'detail_value': 'Values early updates',
                            'is_conversation_cue': False,
                        }
                    ],
                    'observations': [],
                },
            },
            format='json',
        )
        self.assertEqual(
            unchanged_carry.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(unchanged_carry.data['revision'], 4)

        changed_carry = self.client.patch(
            reverse('journal-reflection-detail', args=[reflection_id]),
            {
                'expected_revision': 4,
                'carry_forward': {
                    'facts': [
                        {
                            'id': fact_item['id'],
                            'target_contact_id': self.contact.id,
                            'category_id': fact_category.id,
                            'label': 'Communication',
                            'detail_value': 'Changed after publication',
                        }
                    ],
                    'observations': [],
                },
            },
            format='json',
        )
        self.assertEqual(
            changed_carry.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn('carry_forward', changed_carry.data)

        added_carry = self.client.patch(
            reverse('journal-reflection-detail', args=[reflection_id]),
            {
                'expected_revision': 4,
                'carry_forward': {
                    'facts': [
                        {
                            'id': fact_item['id'],
                            'target_contact_id': self.contact.id,
                            'category_id': fact_category.id,
                            'label': 'Communication',
                            'detail_value': 'Values early updates',
                            'is_conversation_cue': False,
                        },
                        {
                            'target_contact_id': self.contact.id,
                            'category_id': fact_category.id,
                            'label': 'New item',
                            'detail_value': 'Added after completion',
                        },
                    ],
                    'observations': [],
                },
            },
            format='json',
        )
        self.assertEqual(
            added_carry.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn('carry_forward', added_carry.data)

        removed_carry = self.client.patch(
            reverse('journal-reflection-detail', args=[reflection_id]),
            {
                'expected_revision': 4,
                'carry_forward': {
                    'facts': [],
                    'observations': [],
                },
            },
            format='json',
        )
        self.assertEqual(
            removed_carry.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn('carry_forward', removed_carry.data)

        fact.refresh_from_db()
        self.assertEqual(fact.detail_value, 'Values early updates')
        self.assertEqual(str(fact.source_item_id), str(fact_item['id']))

        repeated = self.client.post(
            reverse('journal-reflection-complete', args=[reflection_id]),
            {'expected_revision': 1},
            format='json',
        )
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Fact.objects.filter(source_reflection_id=reflection_id).count(),
            1,
        )
        self.assertEqual(repeated.data['revision'], 4)

    def test_reflection_cover_can_be_cleared_and_cannot_be_sensitive(self):
        media = MediaAsset.objects.create(
            user=self.user,
            file='media/test-cover.jpg',
            original_filename='test-cover.jpg',
            content_type='image/jpeg',
            file_size=12,
        )
        payload = {
            'format': 'free',
            'title': 'Reflection with cover',
            'detail': {'body': 'A meaningful reflection body.'},
            'attachments': [
                {
                    'media_asset_id': media.id,
                    'is_sensitive': False,
                }
            ],
            'cover_media_asset_id': media.id,
        }
        created = self.client.post(
            reverse('journal-reflection-list'),
            payload,
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(created.data['cover_attachment_id'])
        self.assertTrue(created.data['attachments'][0]['is_cover'])
        self.assertEqual(
            created.data['attachments'][0]['media_asset']['id'],
            media.id,
        )
        media_created = created.data['attachments'][0]['media_asset'][
            'created_timestamp'
        ]
        self.assertIsInstance(media_created, str)
        self.assertTrue(media_created)

        cleared = self.client.patch(
            reverse(
                'journal-reflection-detail',
                args=[created.data['id']],
            ),
            {
                'expected_revision': 1,
                'cover_media_asset_id': None,
            },
            format='json',
        )
        self.assertEqual(cleared.status_code, status.HTTP_200_OK)
        self.assertIsNone(cleared.data['cover_attachment_id'])
        self.assertFalse(cleared.data['attachments'][0]['is_cover'])

        payload['title'] = 'Sensitive cover attempt'
        payload['attachments'][0]['is_sensitive'] = True
        rejected = self.client.post(
            reverse('journal-reflection-list'),
            payload,
            format='json',
        )
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cover_media_asset_id', rejected.data)

        audio = MediaAsset.objects.create(
            user=self.user,
            file='media/test-cover.mp3',
            original_filename='test-cover.mp3',
            content_type='audio/mpeg',
            file_size=12,
        )
        rejected_audio = self.client.post(
            reverse('journal-reflection-list'),
            {
                'format': 'free',
                'title': 'Audio cover attempt',
                'detail': {'body': 'A meaningful reflection body.'},
                'attachments': [
                    {
                        'media_asset_id': audio.id,
                        'is_sensitive': False,
                    }
                ],
                'cover_media_asset_id': audio.id,
            },
            format='json',
        )
        self.assertEqual(
            rejected_audio.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn('cover_media_asset_id', rejected_audio.data)

    def test_feed_excludes_retained_exercise_rows(self):
        occurred_at = timezone.now()
        log = Log.objects.create(
            user=self.user,
            event=self.event,
            format='legacy',
            status='completed',
            title='Legacy log',
            occurred_at=occurred_at,
            completed_at=occurred_at,
        )
        reflection = Reflection.objects.create(
            user=self.user,
            event=self.event,
            format='legacy',
            status='completed',
            title='Legacy reflection',
            occurred_at=occurred_at,
            completed_at=occurred_at,
        )
        Exercise.objects.create(
            user=self.user,
            event=self.event,
            title='Retained exercise',
            pre_measurement=1,
            post_measurement=2,
        )

        response = self.client.get(reverse('journal-feed'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(
            {item['id'] for item in response.data['results']},
            {str(log.id), str(reflection.id)},
        )
        self.assertEqual(
            {item['family'] for item in response.data['results']},
            {'log', 'reflection'},
        )
        result_by_id = {
            item['id']: item for item in response.data['results']
        }
        self.assertEqual(result_by_id[str(log.id)]['format'], 'legacy')
        self.assertEqual(
            result_by_id[str(reflection.id)]['format'],
            'legacy',
        )

        episode = Log.objects.create(
            user=self.user,
            format=Log.FORMAT_EPISODE,
            status=Log.STATUS_COMPLETED,
            title='Structured episode',
            occurred_at=occurred_at,
            completed_at=occurred_at,
        )
        log_family = self.client.get(
            reverse('journal-feed'),
            {'family': 'log'},
        )
        self.assertEqual(log_family.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item['id'] for item in log_family.data['results']},
            {str(log.id), str(episode.id)},
        )
        episode_only = self.client.get(
            reverse('journal-feed'),
            {'format': Log.FORMAT_EPISODE},
        )
        self.assertEqual(episode_only.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item['id'] for item in episode_only.data['results']],
            [str(episode.id)],
        )

        legacy_edit = self.client.patch(
            reverse('journal-log-detail', args=[log.id]),
            {
                'expected_revision': 1,
                'title': 'Legacy edit attempt',
            },
            format='json',
        )
        self.assertEqual(
            legacy_edit.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn('format', legacy_edit.data)

    def test_feed_summary_is_bounded_plain_text_and_privacy_safe(self):
        media = MediaAsset.objects.create(
            user=self.user,
            file='media/sensitive-summary-test.jpg',
            original_filename='sensitive-summary-test.jpg',
            content_type='image/jpeg',
            file_size=12,
            alt_text='SECRET ALT TEXT',
            caption='SECRET CAPTION',
        )
        long_focus = 'A meaningful quiet moment ' + ('continued ' * 30)
        moment = self.client.post(
            reverse('journal-reflection-list'),
            {
                'format': 'moment',
                'title': '',
                'detail': {'focus_moment': long_focus},
                'attachments': [
                    {
                        'media_asset_id': media.id,
                        'is_sensitive': True,
                    }
                ],
            },
            format='json',
        )
        self.assertEqual(moment.status_code, status.HTTP_201_CREATED)
        sensitive_attachment_id = moment.data['attachments'][0]['id']
        Reflection.objects.filter(pk=moment.data['id']).update(
            cover_attachment_id=sensitive_attachment_id,
        )

        response = self.client.get(
            reverse('journal-feed'),
            {'search': 'meaningful quiet moment'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        summary = response.data['results'][0]['summary']
        self.assertIsInstance(summary, str)
        self.assertLessEqual(len(summary), 160)
        self.assertTrue(summary.startswith('Focus: A meaningful quiet moment'))
        self.assertNotIn('SECRET ALT TEXT', summary)
        self.assertNotIn('SECRET CAPTION', summary)
        self.assertIsNone(response.data['results'][0]['cover'])

        private_media_search = self.client.get(
            reverse('journal-feed'),
            {'search': 'SECRET ALT TEXT'},
        )
        self.assertEqual(private_media_search.status_code, status.HTTP_200_OK)
        self.assertEqual(private_media_search.data['count'], 0)

        secret_body = 'PRIVATE FREE REFLECTION BODY'
        free = self.client.post(
            reverse('journal-reflection-list'),
            {
                'format': 'free',
                'title': 'Free summary privacy',
                'detail': {'body': secret_body},
            },
            format='json',
        )
        self.assertEqual(free.status_code, status.HTTP_201_CREATED)
        response = self.client.get(
            reverse('journal-feed'),
            {'search': 'Free summary privacy'},
        )
        free_summary = response.data['results'][0]['summary']
        self.assertIsInstance(free_summary, str)
        self.assertEqual(free_summary, '')
        self.assertNotIn(secret_body, free_summary)

        private_body_search = self.client.get(
            reverse('journal-feed'),
            {'search': secret_body},
        )
        self.assertEqual(private_body_search.status_code, status.HTTP_200_OK)
        self.assertEqual(private_body_search.data['count'], 0)

    def test_feed_searches_visible_social_energy_summary_labels(self):
        log = Log.objects.create(
            user=self.user,
            format=Log.FORMAT_SOCIAL_ENERGY,
            title='',
        )
        SocialEnergyLogDetail.objects.create(
            log=log,
            battery_effect='reduced',
            mood_shift='improved',
            behavioral_effect='quieter',
        )

        response = self.client.get(
            reverse('journal-feed'),
            {'search': 'Lower battery'},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(log.id))
        self.assertIn('Lower battery', response.data['results'][0]['summary'])

    def test_exercise_is_not_exposed_in_admin(self):
        self.assertNotIn(Exercise, admin.site._registry)

    def test_custom_lookup_is_owner_scoped(self):
        created = self.client.post(
            reverse('journal-emotion-state-list'),
            {'name': 'Tender'},
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertFalse(created.data['is_system_default'])

        self.client.force_authenticate(self.other_user)
        response = self.client.get(reverse('journal-emotion-state-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            created.data['id'],
            {item['id'] for item in response.data},
        )

    def test_episode_categories_match_the_canonical_concepts(self):
        response = self.client.get(
            reverse('journal-episode-category-list')
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {
                item['code']
                for item in response.data
                if item['is_system_default']
            },
            {
                'mood',
                'thought_pattern',
                'involuntary_response',
                'symptoms',
            },
        )

    def test_event_deletion_unlinks_instead_of_deleting_journal(self):
        log = Log.objects.create(
            user=self.user,
            event=self.event,
            format='legacy',
            status='completed',
            title='Retained log',
        )

        Event.objects.filter(pk=self.event.pk).delete()

        log.refresh_from_db()
        self.assertIsNone(log.event_id)

    def test_patterns_only_count_completed_logs(self):
        occurred_at = timezone.now()
        completed = Log.objects.create(
            user=self.user,
            format='social_energy',
            status='completed',
            title='Completed energy',
            occurred_at=occurred_at,
            completed_at=occurred_at,
        )
        SocialEnergyLogDetail.objects.create(
            log=completed,
            battery_effect='reduced',
            mood_shift='improved',
            behavioral_effect='quieter',
            interaction_context='one_on_one',
        )
        draft = Log.objects.create(
            user=self.user,
            format='social_energy',
            status='draft',
            title='Draft energy',
            occurred_at=occurred_at,
        )
        SocialEnergyLogDetail.objects.create(
            log=draft,
            battery_effect='increased',
        )

        response = self.client.get(reverse('journal-log-patterns'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 1)
        self.assertEqual(response.data['by_format'], {'social_energy': 1})


    def test_patterns_group_legacy_logs_as_unspecified(self):
        occurred_at = timezone.now()
        Log.objects.create(
            user=self.user,
            format=Log.FORMAT_LEGACY,
            status=Log.STATUS_COMPLETED,
            title='Retained log',
            occurred_at=occurred_at,
            completed_at=occurred_at,
        )
        Log.objects.create(
            user=self.user,
            format=Log.FORMAT_EPISODE,
            status=Log.STATUS_COMPLETED,
            title='Structured episode',
            occurred_at=occurred_at,
            completed_at=occurred_at,
        )

        response = self.client.get(reverse('journal-log-patterns'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 2)
        self.assertEqual(
            response.data['by_format'],
            {'episode': 1, 'unspecified': 1},
        )
        self.assertEqual(
            sum(response.data['by_format'].values()),
            response.data['total'],
        )
        self.assertNotIn('legacy', response.data['by_format'])
        episode_only = self.client.get(
            reverse('journal-log-patterns'),
            {'format': Log.FORMAT_EPISODE},
        )
        self.assertEqual(episode_only.status_code, status.HTTP_200_OK)
        self.assertEqual(episode_only.data['total'], 1)
        self.assertEqual(
            episode_only.data['by_format'],
            {'episode': 1},
        )
