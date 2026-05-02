from django.test import TestCase

from contacts.tests.factories import ContactFactory
from events.models import EventParticipant
from events.serializers import EventListSerializer, EventSerializer
from journals.models import Log

from .factories import EventFactory


class EventSerializerTests(TestCase):
    def test_create_writes_participants_from_participant_ids(self):
        event = EventFactory()
        contact = ContactFactory(user=event.user)
        serializer = EventSerializer(
            data={
                "title": "Dinner",
                "event_timestamp": event.event_timestamp.isoformat(),
                "participant_ids": [contact.id],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        created = serializer.save(user=event.user)

        self.assertEqual(created.user, event.user)
        self.assertTrue(
            EventParticipant.objects.filter(event=created, contact=contact).exists()
        )

    def test_serialized_detail_includes_participants_and_journaled(self):
        event = EventFactory()
        contact = ContactFactory(user=event.user, first_name="Ada")
        EventParticipant.objects.create(event=event, contact=contact)
        Log.objects.create(user=event.user, event=event, title="Log", body="Body")

        data = EventSerializer(event).data

        self.assertTrue(data["journaled"])
        self.assertEqual(len(data["participants"]), 1)
        self.assertEqual(data["participants"][0]["contact"]["id"], contact.id)
        self.assertNotIn("participant_ids", data)

    def test_list_serializer_includes_participant_count_and_journaled(self):
        event = EventFactory()
        contact = ContactFactory(user=event.user)
        EventParticipant.objects.create(event=event, contact=contact)

        data = EventListSerializer(event).data

        self.assertEqual(data["participant_count"], 1)
        self.assertFalse(data["journaled"])
