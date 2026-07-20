from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import ContactFactory, UserFactory
from journals.models import Log, Reflection
from media.models import MediaAsset

from events.models import (
    EventChapter,
    EventChapterParticipant,
    EventMedia,
    EventMediaCrop,
    EventParticipant,
)

from .factories import EventFactory


class EventChapterAndMediaApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(self.user)
        self.event = EventFactory(
            user=self.user,
            title='A long afternoon',
            description='The whole Event perspective.',
            event_timestamp=timezone.now(),
            end_timestamp=timezone.now() + timedelta(hours=4),
            location_label='The park',
        )
        self.contact = ContactFactory(user=self.user)
        EventParticipant.objects.create(
            event=self.event,
            contact=self.contact,
        )

    def _chapter(self, **values):
        defaults = {
            'event': self.event,
            'title': 'Chapter',
            'position': self.event.chapters.count(),
            'start_timestamp': self.event.event_timestamp,
        }
        defaults.update(values)
        return EventChapter.objects.create(**defaults)

    def _image(self, *, user=None, name='event.jpg'):
        return MediaAsset.objects.create(
            user=user or self.user,
            file=f'media/{name}',
            original_filename=name,
            claimed_content_type='image/jpeg',
            content_type='image/jpeg',
            detected_content_type='image/jpeg',
            file_size=128,
            status=MediaAsset.STATUS_READY,
            width=1200,
            height=800,
            alt_text='Friends spending time together',
        )

    def test_event_detail_projects_legacy_chapter_without_writing(self):
        log = Log.objects.create(
            user=self.user,
            event=self.event,
            title='Whole Event log',
            body='A compact legacy excerpt.',
        )

        response = self.client.get(
            reverse('event-detail', args=[self.event.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['chapter_mode'], 'projected')
        self.assertEqual(response.data['chapters'], [])
        projection = response.data['legacy_chapter']
        self.assertTrue(projection['is_projection'])
        self.assertIsNone(projection['id'])
        self.assertEqual(projection['title'], self.event.title)
        self.assertEqual(projection['participant_count'], 1)
        self.assertEqual(
            projection['participant_preview'][0]['id'],
            self.contact.id,
        )
        self.assertEqual(projection['media_count'], 0)
        self.assertIsNone(projection['thumbnail'])
        self.assertEqual(projection['journals']['logs'][0]['id'], log.id)
        self.assertEqual(
            projection['journals']['logs'][0]['summary'],
            'A compact legacy excerpt.',
        )
        self.assertEqual(EventChapter.objects.count(), 0)

    def test_inherited_participants_keep_one_order_and_detail_has_header_fields(self):
        last_contact = ContactFactory(user=self.user)
        middle_contact = ContactFactory(user=self.user)
        EventParticipant.objects.create(
            event=self.event,
            contact=last_contact,
        )
        EventParticipant.objects.create(
            event=self.event,
            contact=middle_contact,
        )
        chapter = self._chapter(inherits_event_participants=True)

        event_response = self.client.get(
            reverse('event-detail', args=[self.event.id]),
        )
        chapter_response = self.client.get(
            reverse(
                'event-chapter-detail',
                args=[self.event.id, chapter.id],
            ),
        )

        self.assertEqual(event_response.status_code, status.HTTP_200_OK)
        self.assertEqual(chapter_response.status_code, status.HTTP_200_OK)
        expected_ids = [
            participant.contact_id
            for participant in self.event.participants.order_by('id')
        ]
        self.assertEqual(
            [
                participant['contact']['id']
                for participant in event_response.data['participants']
            ],
            expected_ids,
        )
        self.assertEqual(
            [
                contact['id']
                for contact in event_response.data['chapters'][0][
                    'participant_preview'
                ]
            ],
            expected_ids[:3],
        )
        self.assertEqual(
            [
                contact['id']
                for contact in chapter_response.data['effective_participants']
            ],
            expected_ids,
        )
        self.assertEqual(
            chapter_response.data['participant_count'],
            len(expected_ids),
        )
        self.assertEqual(
            [
                contact['id']
                for contact in chapter_response.data['participant_preview']
            ],
            expected_ids[:3],
        )
        self.assertEqual(chapter_response.data['media_count'], 0)
        self.assertIsNone(chapter_response.data['thumbnail'])

    def test_adding_to_projected_event_materializes_then_appends(self):
        response = self.client.post(
            reverse('event-chapter-list', args=[self.event.id]),
            {
                'title': 'The walk home',
                'start_timestamp': (
                    self.event.event_timestamp + timedelta(hours=2)
                ).isoformat(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        chapters = list(self.event.chapters.order_by('position'))
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0].title, self.event.title)
        self.assertEqual(chapters[0].note, self.event.description)
        self.assertEqual(chapters[1].title, 'The walk home')
        self.assertEqual(chapters[1].position, 1)
        self.assertEqual(response.data['id'], str(chapters[1].id))

    def test_materialize_is_idempotent(self):
        url = reverse(
            'event-chapter-materialize-legacy',
            args=[self.event.id],
        )

        created = self.client.post(url, {}, format='json')
        repeated = self.client.post(url, {}, format='json')

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(created.data['id'], repeated.data['id'])
        self.assertEqual(self.event.chapters.count(), 1)

    def test_materialize_truncates_a_legacy_event_title_to_chapter_limit(self):
        self.event.title = 'A' * 255
        self.event.save(update_fields=['title'])

        response = self.client.post(
            reverse('event-chapter-materialize-legacy', args=[self.event.id]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'A' * 120)

    def test_materialize_edit_is_atomic_and_replayable(self):
        url = reverse(
            'event-chapter-materialize-legacy',
            args=[self.event.id],
        )
        invalid = self.client.post(
            url,
            {
                'title': 'Edited projection',
                'start_timestamp': (
                    self.event.event_timestamp - timedelta(seconds=1)
                ).isoformat(),
            },
            format='json',
        )

        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.event.chapters.count(), 0)

        payload = {
            'title': 'Edited projection',
            'location_label': '',
            'note': 'The edited chapter note.',
            'inherits_event_participants': False,
            'participant_ids': [self.contact.id],
        }
        created = self.client.post(url, payload, format='json')
        repeated = self.client.post(url, payload, format='json')

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(created.data['id'], repeated.data['id'])
        chapter = self.event.chapters.get()
        self.assertEqual(chapter.title, 'Edited projection')
        self.assertEqual(chapter.location_label, '')
        self.assertFalse(chapter.inherits_event_participants)
        self.assertEqual(
            list(chapter.participant_links.values_list('contact_id', flat=True)),
            [self.contact.id],
        )

    def test_chapter_time_range_and_exact_reorder_are_validated(self):
        invalid = self.client.post(
            reverse('event-chapter-list', args=[self.event.id]),
            {
                'title': 'Before the Event',
                'start_timestamp': (
                    self.event.event_timestamp - timedelta(seconds=1)
                ).isoformat(),
            },
            format='json',
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_timestamp', invalid.data)

        first = self._chapter(title='First', position=0)
        second = self._chapter(title='Second', position=1)
        reordered = self.client.put(
            reverse('event-chapter-reorder', args=[self.event.id]),
            {'chapter_ids': [str(second.id), str(first.id)]},
            format='json',
        )
        self.assertEqual(reordered.status_code, status.HTTP_200_OK)
        self.assertEqual(
            list(self.event.chapters.values_list('id', flat=True)),
            [second.id, first.id],
        )

        incomplete = self.client.put(
            reverse('event-chapter-reorder', args=[self.event.id]),
            {'chapter_ids': [str(first.id)]},
            format='json',
        )
        self.assertEqual(incomplete.status_code, status.HTTP_400_BAD_REQUEST)

    def test_event_participant_removal_is_blocked_for_explicit_chapter(self):
        chapter = self._chapter(inherits_event_participants=False)
        EventChapterParticipant.objects.create(
            chapter=chapter,
            contact=self.contact,
            display_order=0,
        )

        response = self.client.patch(
            reverse('event-detail', args=[self.event.id]),
            {'participants': []},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(str(chapter.id), response.data['participants']['chapter_ids'])
        self.assertTrue(
            EventParticipant.objects.filter(
                event=self.event,
                contact=self.contact,
            ).exists()
        )

    def test_journal_chapter_sets_event_and_summaries_remain_separate(self):
        chapter = self._chapter()
        whole = Reflection.objects.create(
            user=self.user,
            event=self.event,
            title='Whole Event reflection',
        )
        created = self.client.post(
            reverse('journal-reflection-list'),
            {
                'format': 'free',
                'chapter_id': str(chapter.id),
                'title': 'Chapter reflection',
                'detail': {'body': 'The light changed as we walked.'},
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        reflection = Reflection.objects.get(pk=created.data['id'])
        self.assertEqual(reflection.event, self.event)
        self.assertEqual(reflection.chapter, chapter)

        event_detail = self.client.get(
            reverse('event-detail', args=[self.event.id]),
        )
        chapter_detail = self.client.get(
            reverse(
                'event-chapter-detail',
                args=[self.event.id, chapter.id],
            )
        )
        self.assertEqual(
            event_detail.data['journals']['reflections'][0]['id'],
            whole.id,
        )
        self.assertEqual(event_detail.data['journals']['reflection_count'], 1)
        self.assertEqual(chapter_detail.data['journals']['reflection_count'], 1)
        self.assertEqual(
            chapter_detail.data['journals']['reflections'][0]['summary'],
            'The light changed as we walked.',
        )
        self.assertEqual(
            set(chapter_detail.data['journals']['reflections'][0]),
            {
                'id',
                'family',
                'format',
                'status',
                'title',
                'summary',
                'primary_contact',
                'occurred_at',
                'created_timestamp',
                'updated_timestamp',
            },
        )

        whole_feed = self.client.get(
            reverse('journal-feed'),
            {'event': self.event.id, 'chapter': 'event'},
        )
        chapter_feed = self.client.get(
            reverse('journal-feed'),
            {'event': self.event.id, 'chapter': str(chapter.id)},
        )
        self.assertEqual(whole_feed.data['count'], 1)
        self.assertEqual(chapter_feed.data['count'], 1)
        self.assertEqual(whole_feed.data['results'][0]['id'], str(whole.id))
        self.assertEqual(chapter_feed.data['results'][0]['id'], created.data['id'])
        self.assertIsNone(whole_feed.data['results'][0]['chapter'])
        self.assertEqual(
            chapter_feed.data['results'][0]['chapter'],
            {
                'id': chapter.id,
                'title': chapter.title,
                'position': chapter.position,
            },
        )

    def test_chapter_delete_preserves_journal_and_promotes_media_without_crop(self):
        chapter = self._chapter()
        journal = Log.objects.create(
            user=self.user,
            event=self.event,
            chapter=chapter,
            title='Retained chapter log',
        )
        attachment = EventMedia.objects.create(
            event=self.event,
            chapter=chapter,
            media_asset=self._image(),
            display_order=0,
            alt_text='A chapter image',
            is_cover=True,
        )
        EventMediaCrop.objects.create(
            event_media=attachment,
            crop_kind=EventMediaCrop.KIND_CHAPTER_CAROUSEL,
            x=0,
            y=0,
            width=1,
            height=1,
        )

        response = self.client.delete(
            reverse(
                'event-chapter-detail',
                args=[self.event.id, chapter.id],
            )
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        journal.refresh_from_db()
        attachment.refresh_from_db()
        self.assertEqual(journal.event, self.event)
        self.assertIsNone(journal.chapter_id)
        self.assertIsNone(attachment.chapter_id)
        self.assertEqual(attachment.display_order, 0)
        self.assertTrue(attachment.is_cover)
        self.assertFalse(attachment.crops.exists())

    def test_event_media_is_owner_scoped_and_crop_kind_matches_scope(self):
        other_asset = self._image(user=self.other_user, name='private.jpg')
        hidden = self.client.post(
            reverse('event-media-list', args=[self.event.id]),
            {
                'media_asset_id': other_asset.id,
                'alt_text': 'Private',
            },
            format='json',
        )
        self.assertEqual(hidden.status_code, status.HTTP_400_BAD_REQUEST)

        asset = self._image()
        created = self.client.post(
            reverse('event-media-list', args=[self.event.id]),
            {
                'media_asset_id': asset.id,
                'alt_text': 'A wide Event cover',
                'is_cover': True,
                'focal_x': 0.4,
                'focal_y': 0.6,
                'crops': [
                    {
                        'crop_kind': 'event_cover',
                        'x': 0.1,
                        'y': 0.1,
                        'width': 0.8,
                        'height': 0.8,
                    }
                ],
            },
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertIn(
            f'{reverse("media-content", args=[asset.id])}?token=',
            created.data['media_asset']['content_url'],
        )
        self.assertEqual(created.data['crops'][0]['crop_kind'], 'event_cover')

        detail = self.client.get(reverse('event-detail', args=[self.event.id]))
        self.assertEqual(detail.data['media_summary']['total_count'], 1)
        self.assertEqual(detail.data['media_summary']['image_count'], 1)
        self.assertEqual(len(detail.data['media_summary']['previews']), 1)

        chapter = self._chapter()
        wrong_crop = self.client.post(
            reverse('event-media-list', args=[self.event.id]),
            {
                'media_asset_id': self._image(name='chapter.jpg').id,
                'chapter_id': str(chapter.id),
                'alt_text': 'A chapter photo',
                'crops': [
                    {
                        'crop_kind': 'event_cover',
                        'x': 0,
                        'y': 0,
                        'width': 1,
                        'height': 1,
                    }
                ],
            },
            format='json',
        )
        self.assertEqual(wrong_crop.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('crops', wrong_crop.data)

    def test_event_media_update_and_delete_lock_only_the_attachment(self):
        asset = self._image(name='mutable.jpg')
        attachment = EventMedia.objects.create(
            event=self.event,
            media_asset=asset,
            display_order=0,
            alt_text='Before',
        )
        url = reverse(
            'event-media-detail',
            args=[self.event.id, attachment.id],
        )

        updated = self.client.patch(
            url,
            {'alt_text': 'After', 'focal_x': 0.25},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data['alt_text'], 'After')
        self.assertEqual(updated.data['focal_x'], 0.25)

        removed = self.client.delete(url)
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(EventMedia.objects.filter(pk=attachment.id).exists())
        self.assertTrue(MediaAsset.objects.filter(pk=asset.id, is_active=True).exists())

    def test_event_delete_cascades_chapters_and_attachments_but_keeps_asset(self):
        chapter = self._chapter()
        asset = self._image(name='retained-original.jpg')
        EventMedia.objects.create(
            event=self.event,
            chapter=chapter,
            media_asset=asset,
            display_order=0,
            alt_text='A retained original',
        )
        journal = Log.objects.create(
            user=self.user,
            event=self.event,
            chapter=chapter,
            title='Retained journal',
        )

        response = self.client.delete(
            reverse('event-detail', args=[self.event.id]),
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        journal.refresh_from_db()
        self.assertIsNone(journal.event_id)
        self.assertIsNone(journal.chapter_id)
        self.assertTrue(MediaAsset.objects.filter(pk=asset.id).exists())

    def test_chapter_collection_query_count_does_not_grow_with_chapters(self):
        first = self._chapter(title='First')
        EventMedia.objects.create(
            event=self.event,
            chapter=first,
            media_asset=self._image(name='first.jpg'),
            display_order=0,
            alt_text='First chapter',
        )
        url = reverse('event-chapter-list', args=[self.event.id])

        with CaptureQueriesContext(connection) as initial_queries:
            initial = self.client.get(url)
        for position in range(1, 6):
            self._chapter(title=f'Chapter {position + 1}', position=position)
        with CaptureQueriesContext(connection) as expanded_queries:
            expanded = self.client.get(url)

        self.assertEqual(initial.status_code, status.HTTP_200_OK)
        self.assertEqual(expanded.status_code, status.HTTP_200_OK)
        self.assertEqual(len(initial_queries), len(expanded_queries))

    def test_detail_endpoints_meet_documented_query_budgets(self):
        chapter = self._chapter(title='Measured chapter')
        attachment = EventMedia.objects.create(
            event=self.event,
            chapter=chapter,
            media_asset=self._image(name='measured.jpg'),
            display_order=0,
            alt_text='Measured chapter image',
        )
        EventMediaCrop.objects.create(
            event_media=attachment,
            crop_kind=EventMediaCrop.KIND_CHAPTER_CAROUSEL,
            x=0,
            y=0,
            width=1,
            height=1,
        )
        Log.objects.create(
            user=self.user,
            event=self.event,
            chapter=chapter,
            title='Measured chapter Log',
        )
        Reflection.objects.create(
            user=self.user,
            event=self.event,
            title='Measured Event Reflection',
        )

        with CaptureQueriesContext(connection) as event_queries:
            event_response = self.client.get(
                reverse('event-detail', args=[self.event.id]),
            )
        with CaptureQueriesContext(connection) as chapter_queries:
            chapter_response = self.client.get(
                reverse(
                    'event-chapter-detail',
                    args=[self.event.id, chapter.id],
                ),
            )

        self.assertEqual(event_response.status_code, status.HTTP_200_OK)
        self.assertEqual(chapter_response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(event_queries), 10)
        self.assertLessEqual(len(chapter_queries), 8)

    def test_foreign_nested_parent_and_child_return_404(self):
        other_event = EventFactory(user=self.other_user)
        other_chapter = EventChapter.objects.create(
            event=other_event,
            title='Private chapter',
            position=0,
        )

        parent = self.client.get(
            reverse('event-chapter-list', args=[other_event.id]),
        )
        child = self.client.get(
            reverse(
                'event-chapter-detail',
                args=[self.event.id, other_chapter.id],
            )
        )

        self.assertEqual(parent.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(child.status_code, status.HTTP_404_NOT_FOUND)

    def test_event_media_rejects_malformed_chapter_filter(self):
        response = self.client.get(
            reverse('event-media-list', args=[self.event.id]),
            {'chapter_id': 'not-a-uuid'},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('chapter_id', response.data)
