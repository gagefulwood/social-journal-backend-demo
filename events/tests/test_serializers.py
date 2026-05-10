from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from contacts.tests.factories import ContactFactory
from events.models import EventParticipant
from events.serializers import EventListSerializer, EventSerializer
from journals.models import Exercise, Log, Reflection

from .factories import EventFactory


class EventSerializerTests(TestCase):
    def test_create_writes_participants_from_participants(self):
        event = EventFactory()
        contact = ContactFactory(user=event.user)
        serializer = EventSerializer(
            data={
                "title": "Dinner",
                "event_timestamp": event.event_timestamp.isoformat(),
                "end_timestamp": (
                    event.event_timestamp + timezone.timedelta(hours=1)
                ).isoformat(),
                "location_label": "Cafe",
                "tier": "milestone",
                "participants": [contact.id],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        created = serializer.save(user=event.user)

        self.assertEqual(created.user, event.user)
        self.assertEqual(created.location_label, "Cafe")
        self.assertEqual(created.tier, "milestone")
        self.assertTrue(
            EventParticipant.objects.filter(event=created, contact=contact).exists()
        )

    def test_create_rejects_other_users_participants(self):
        event = EventFactory()
        contact = ContactFactory()
        serializer = EventSerializer(
            data={
                "title": "Dinner",
                "event_timestamp": event.event_timestamp.isoformat(),
                "participants": [contact.id],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        with self.assertRaises(ValidationError):
            serializer.save(user=event.user)

    def test_serialized_detail_includes_participants_journaled_and_journals(self):
        event = EventFactory()
        contact = ContactFactory(user=event.user, first_name="Ada")
        EventParticipant.objects.create(event=event, contact=contact)
        log = Log.objects.create(user=event.user, event=event, title="Log", body="Body")

        data = EventSerializer(event).data

        self.assertTrue(data["journaled"])
        self.assertEqual(len(data["participants"]), 1)
        self.assertEqual(data["participants"][0]["contact"]["id"], contact.id)
        self.assertEqual(data["journals"]["log"]["id"], log.id)
        self.assertEqual(data["journals"]["log"]["kind"], "log")
        self.assertEqual(data["journals"]["log"]["title"], "Log")
        self.assertIsNone(data["journals"]["reflection"])
        self.assertIsNone(data["journals"]["exercise"])

    def test_serialized_detail_includes_reflection_and_exercise_summaries(self):
        event = EventFactory()
        reflection = Reflection.objects.create(
            user=event.user,
            event=event,
            title="Reflection",
            clarity_check="Clear",
        )
        exercise = Exercise.objects.create(
            user=event.user,
            event=event,
            title="Exercise",
            pre_measurement=3,
            post_measurement=8,
        )

        data = EventSerializer(event).data

        self.assertEqual(data["journals"]["reflection"]["id"], reflection.id)
        self.assertEqual(data["journals"]["reflection"]["kind"], "reflection")
        self.assertEqual(data["journals"]["reflection"]["title"], "Reflection")
        self.assertEqual(data["journals"]["reflection"]["clarity_check"], "Clear")
        self.assertEqual(data["journals"]["exercise"]["id"], exercise.id)
        self.assertEqual(data["journals"]["exercise"]["kind"], "exercise")
        self.assertEqual(data["journals"]["exercise"]["title"], "Exercise")
        self.assertEqual(data["journals"]["exercise"]["measurement_delta"], 5)

    def test_update_rejects_event_timestamp_change(self):
        event = EventFactory()
        serializer = EventSerializer(
            event,
            data={
                "event_timestamp": (
                    event.event_timestamp + timezone.timedelta(days=1)
                ).isoformat()
            },
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("event_timestamp", serializer.errors)

    def test_update_replaces_participants(self):
        event = EventFactory()
        removed_contact = ContactFactory(user=event.user)
        kept_contact = ContactFactory(user=event.user)
        added_contact = ContactFactory(user=event.user)
        EventParticipant.objects.create(event=event, contact=removed_contact)
        EventParticipant.objects.create(event=event, contact=kept_contact)
        serializer = EventSerializer(
            event,
            data={"participants": [kept_contact.id, added_contact.id]},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        contact_ids = set(
            EventParticipant.objects.filter(event=event).values_list(
                "contact_id",
                flat=True,
            )
        )
        self.assertEqual(contact_ids, {kept_contact.id, added_contact.id})

    def test_list_serializer_includes_participant_count_and_journaled(self):
        event = EventFactory()
        contact = ContactFactory(user=event.user)
        EventParticipant.objects.create(event=event, contact=contact)

        data = EventListSerializer(event).data

        self.assertEqual(data["participant_count"], 1)
        self.assertFalse(data["journaled"])
        self.assertEqual(data["tier"], "routine")
        self.assertIn("location_label", data)
