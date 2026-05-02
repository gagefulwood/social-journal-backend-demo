from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import ContactFactory, UserFactory
from events.models import Event, EventParticipant
from journals.models import Log

from .factories import EventFactory


class EventViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_paginated_events_scoped_to_user(self):
        owned_event = EventFactory(user=self.user, title="Owned")
        EventFactory(user=self.other_user, title="Other")

        response = self.client.get(reverse("event-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], owned_event.id)

    def test_create_sets_user_and_participants_from_request(self):
        contact = ContactFactory(user=self.user)

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Dinner",
                "event_timestamp": timezone.now().isoformat(),
                "user": self.other_user.id,
                "participant_ids": [contact.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(id=response.data["id"])
        self.assertEqual(event.user, self.user)
        self.assertTrue(
            EventParticipant.objects.filter(event=event, contact=contact).exists()
        )

    def test_retrieve_returns_404_for_other_users_event(self):
        other_event = EventFactory(user=self.other_user)

        response = self.client.get(reverse("event-detail", args=[other_event.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_includes_journaled_computed_property(self):
        event = EventFactory(user=self.user)

        unjournaled = self.client.get(reverse("event-detail", args=[event.id]))

        self.assertEqual(unjournaled.status_code, status.HTTP_200_OK)
        self.assertFalse(unjournaled.data["journaled"])

        Log.objects.create(user=self.user, event=event, title="Log", body="Body")
        journaled = self.client.get(reverse("event-detail", args=[event.id]))

        self.assertEqual(journaled.status_code, status.HTTP_200_OK)
        self.assertTrue(journaled.data["journaled"])

    def test_partial_update_allows_owner(self):
        event = EventFactory(user=self.user, title="Old")

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"title": "New"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.title, "New")

    def test_partial_update_blocks_other_users_event(self):
        other_event = EventFactory(user=self.other_user, title="Other")

        response = self.client.patch(
            reverse("event-detail", args=[other_event.id]),
            {"title": "Changed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        other_event.refresh_from_db()
        self.assertEqual(other_event.title, "Other")

    def test_delete_removes_event_and_participants(self):
        event = EventFactory(user=self.user)
        contact = ContactFactory(user=self.user)
        EventParticipant.objects.create(event=event, contact=contact)

        response = self.client.delete(reverse("event-detail", args=[event.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Event.objects.filter(id=event.id).exists())
        self.assertFalse(EventParticipant.objects.filter(event_id=event.id).exists())
