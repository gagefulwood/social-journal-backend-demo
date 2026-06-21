from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from contacts.tests.factories import ContactFactory, UserFactory
from events.models import (
    EVENT_IMPACT_CHOICES,
    EVENT_IMPACT_NEGATIVE,
    EVENT_IMPACT_NEUTRAL,
    EVENT_IMPACT_POSITIVE,
    EVENT_TIER_CHOICES,
    EVENT_TIER_MILESTONE,
    EVENT_TIER_ROUTINE,
    Event,
    EventParticipant,
)
from journals.models import Exercise, Log, Reflection

from .factories import EventFactory, EventParticipantFactory


class EventModelTests(TestCase):
    def test_str_returns_title_and_date(self):
        event = EventFactory(
            title="Coffee",
            event_timestamp=timezone.datetime(
                2026,
                5,
                2,
                12,
                0,
                tzinfo=timezone.get_current_timezone(),
            ),
        )

        self.assertIn("Coffee", str(event))
        self.assertIn("2026-05-02", str(event))

    def test_journaled_is_false_without_entries(self):
        event = EventFactory()

        self.assertFalse(event.journaled)

    def test_new_field_defaults(self):
        event = EventFactory()

        self.assertIsNone(event.end_timestamp)
        self.assertEqual(event.location_label, "")
        self.assertEqual(event.tier, EVENT_TIER_ROUTINE)
        self.assertEqual(event.description, "")
        self.assertEqual(event.impact, "")
        self.assertIsNone(event.interaction_mode)
        self.assertIsNone(event.mood)

    def test_tier_choices_include_routine_and_milestone(self):
        choices = dict(EVENT_TIER_CHOICES)

        self.assertEqual(choices[EVENT_TIER_ROUTINE], "Routine")
        self.assertEqual(choices[EVENT_TIER_MILESTONE], "Milestone")

    def test_impact_choices_include_supported_values(self):
        choices = dict(EVENT_IMPACT_CHOICES)

        self.assertEqual(choices[EVENT_IMPACT_NEGATIVE], "Negative")
        self.assertEqual(choices[EVENT_IMPACT_NEUTRAL], "Neutral")
        self.assertEqual(choices[EVENT_IMPACT_POSITIVE], "Positive")

    def test_db_table_is_events(self):
        self.assertEqual(Event._meta.db_table, "events")

    def test_journaled_is_true_with_log(self):
        event = EventFactory()
        Log.objects.create(
            user=event.user,
            event=event,
            title="Logged",
            body="Body",
        )

        self.assertTrue(event.journaled)

    def test_journaled_is_true_with_reflection(self):
        event = EventFactory()
        Reflection.objects.create(
            user=event.user,
            event=event,
            title="Reflection",
        )

        self.assertTrue(event.journaled)

    def test_journaled_is_true_with_exercise(self):
        event = EventFactory()
        Exercise.objects.create(
            user=event.user,
            event=event,
            title="Exercise",
            pre_measurement=1,
            post_measurement=2,
        )

        self.assertTrue(event.journaled)

    def test_upcoming_returns_next_five_events_for_user(self):
        user = UserFactory()
        other_user = UserFactory()
        now = timezone.now()
        expected = [
            EventFactory(user=user, event_timestamp=now + timedelta(days=index + 1))
            for index in range(6)
        ][:5]
        EventFactory(user=user, event_timestamp=now - timedelta(days=1))
        EventFactory(user=other_user, event_timestamp=now + timedelta(days=1))

        events = list(Event.objects.upcoming(user))

        self.assertEqual(events, expected)

    def test_recent_returns_last_five_past_events_for_user(self):
        user = UserFactory()
        other_user = UserFactory()
        now = timezone.now()
        expected = [
            EventFactory(user=user, event_timestamp=now - timedelta(days=index + 1))
            for index in range(6)
        ][:5]
        EventFactory(user=user, event_timestamp=now + timedelta(days=1))
        EventFactory(user=other_user, event_timestamp=now - timedelta(days=1))

        events = list(Event.objects.recent(user))

        self.assertEqual(events, expected)


class EventParticipantModelTests(TestCase):
    def test_str_returns_contact_at_event(self):
        participant = EventParticipantFactory()

        self.assertIn("@", str(participant))
        self.assertIn(str(participant.contact), str(participant))
        self.assertIn(str(participant.event), str(participant))

    def test_unique_event_contact_pair(self):
        event = EventFactory()
        contact = ContactFactory(user=event.user)
        EventParticipant.objects.create(event=event, contact=contact)

        with self.assertRaises(IntegrityError):
            EventParticipant.objects.create(event=event, contact=contact)
