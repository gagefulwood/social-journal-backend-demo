from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from events.models import Event, EventParticipant
from journals.models import Log
from lookups.models import ContextCategory, Mood

from .factories import ContactFactory, UserFactory


class ContactStatisticsSignalTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.contact = ContactFactory(user=self.user)
        self.category = ContextCategory.objects.create(
            user=self.user,
            name="Social",
            color="#4A90E2",
        )

    def test_event_participant_save_recalculates_contact_statistics(self):
        event = Event.objects.create(
            user=self.user,
            title="Coffee",
            event_timestamp=timezone.now(),
            context_category=self.category,
        )

        EventParticipant.objects.create(event=event, contact=self.contact)

        self.contact.refresh_from_db()
        self.assertEqual(self.contact.interaction_frequency_score, 30)
        self.assertEqual(self.contact.relationship_trend, "growing")
        self.assertEqual(self.contact.interaction_diversity_score, 25)
        self.assertEqual(self.contact.connection_strength, 39)

    def test_event_participant_delete_recalculates_contact_statistics(self):
        recent_event = Event.objects.create(
            user=self.user,
            title="Recent",
            event_timestamp=timezone.now(),
            context_category=self.category,
        )
        older_event = Event.objects.create(
            user=self.user,
            title="Older",
            event_timestamp=timezone.now() - timedelta(days=40),
            context_category=self.category,
        )
        recent_participant = EventParticipant.objects.create(
            event=recent_event,
            contact=self.contact,
        )
        EventParticipant.objects.create(event=older_event, contact=self.contact)

        recent_participant.delete()

        self.contact.refresh_from_db()
        self.assertEqual(self.contact.interaction_frequency_score, 10)
        self.assertEqual(self.contact.relationship_trend, "dormant")
        self.assertEqual(self.contact.connection_strength, 9)

    def test_log_save_and_delete_recalculate_event_contacts(self):
        event = Event.objects.create(
            user=self.user,
            title="Dinner",
            event_timestamp=timezone.now(),
            context_category=self.category,
        )
        EventParticipant.objects.create(event=event, contact=self.contact)
        mood = Mood.objects.create(
            user=self.user,
            name="Happy",
            emoji_icon="H",
            polarity=1,
        )

        log = Log.objects.create(
            user=self.user,
            event=event,
            title="Dinner",
            body="Good conversation.",
            mood=mood,
        )

        self.contact.refresh_from_db()
        self.assertEqual(self.contact.sentiment_profile, {"happy": 1})
        self.assertEqual(self.contact.connection_strength, 64)

        log.delete()

        self.contact.refresh_from_db()
        self.assertEqual(self.contact.sentiment_profile, {})
        self.assertEqual(self.contact.connection_strength, 39)
