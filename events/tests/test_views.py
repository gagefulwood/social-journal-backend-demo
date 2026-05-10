from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import ContactFactory, UserFactory
from events.models import Event, EventParticipant
from journals.models import Log
from lookups.models import ContextCategory

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
                "end_timestamp": (timezone.now() + timedelta(hours=2)).isoformat(),
                "location_label": "Cafe",
                "tier": "milestone",
                "participants": [contact.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(id=response.data["id"])
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.location_label, "Cafe")
        self.assertEqual(event.tier, "milestone")
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
        self.assertEqual(journaled.data["journals"]["log"]["title"], "Log")

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

    def test_partial_update_rejects_event_timestamp_change(self):
        event = EventFactory(user=self.user)
        original_timestamp = event.event_timestamp

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"event_timestamp": (original_timestamp + timedelta(days=1)).isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        event.refresh_from_db()
        self.assertEqual(event.event_timestamp, original_timestamp)

    def test_partial_update_replaces_participants_and_triggers_signals(self):
        event = EventFactory(user=self.user)
        removed_contact = ContactFactory(user=self.user)
        kept_contact = ContactFactory(user=self.user)
        added_contact = ContactFactory(user=self.user)
        EventParticipant.objects.create(event=event, contact=removed_contact)
        EventParticipant.objects.create(event=event, contact=kept_contact)

        with patch("contacts.signals.recalculate_contact_statistics") as recalculate:
            response = self.client.patch(
                reverse("event-detail", args=[event.id]),
                {"participants": [kept_contact.id, added_contact.id]},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contact_ids = set(
            EventParticipant.objects.filter(event=event).values_list(
                "contact_id",
                flat=True,
            )
        )
        self.assertEqual(contact_ids, {kept_contact.id, added_contact.id})
        recalculated_contact_ids = {
            call.args[0].id for call in recalculate.call_args_list
        }
        self.assertIn(added_contact.id, recalculated_contact_ids)
        self.assertIn(removed_contact.id, recalculated_contact_ids)
        self.assertNotIn(kept_contact.id, recalculated_contact_ids)

    def test_partial_update_rejects_other_users_participant(self):
        event = EventFactory(user=self.user)
        other_contact = ContactFactory(user=self.other_user)

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"participants": [other_contact.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_filter_by_event_after_and_event_before(self):
        now = timezone.now()
        old_event = EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=10),
        )
        future_event = EventFactory(
            user=self.user,
            event_timestamp=now + timedelta(days=10),
        )

        before_response = self.client.get(
            reverse("event-list"),
            {"event_before": now.isoformat()},
        )

        self.assertEqual(before_response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in before_response.data["results"]}
        self.assertEqual(event_ids, {old_event.id})

        after_response = self.client.get(
            reverse("event-list"),
            {"event_after": now.isoformat()},
        )

        self.assertEqual(after_response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in after_response.data["results"]}
        self.assertEqual(event_ids, {future_event.id})

    def test_filter_supports_now_keyword(self):
        past_event = EventFactory(
            user=self.user,
            event_timestamp=timezone.now() - timedelta(days=1),
        )
        EventFactory(user=self.user, event_timestamp=timezone.now() + timedelta(days=1))

        response = self.client.get(reverse("event-list"), {"event_before": "now"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertEqual(event_ids, {past_event.id})

    def test_filter_by_tier_context_category_and_participant(self):
        category = ContextCategory.objects.create(
            user=self.user,
            name="Social",
            color="#000000",
        )
        contact = ContactFactory(user=self.user)
        matching_event = EventFactory(
            user=self.user,
            tier="milestone",
            context_category=category,
        )
        EventParticipant.objects.create(event=matching_event, contact=contact)
        EventFactory(user=self.user, tier="routine", context_category=category)

        response = self.client.get(
            reverse("event-list"),
            {
                "tier": "milestone",
                "context_category": category.id,
                "participants": str(contact.id),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertEqual(event_ids, {matching_event.id})

    def test_filter_by_title(self):
        matching_event = EventFactory(
            user=self.user,
            title="Dinner with Ada",
            tier="milestone",
        )
        EventFactory(user=self.user, title="Morning coffee", tier="milestone")
        EventFactory(user=self.user, title="Dinner routine", tier="routine")
        EventFactory(user=self.other_user, title="Dinner with Grace", tier="milestone")

        response = self.client.get(
            reverse("event-list"),
            {"title": "dinner", "tier": "milestone"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertEqual(event_ids, {matching_event.id})

    def test_filter_by_journaled(self):
        journaled_event = EventFactory(user=self.user)
        EventFactory(user=self.user)
        Log.objects.create(
            user=self.user,
            event=journaled_event,
            title="Log",
            body="Body",
        )

        response = self.client.get(reverse("event-list"), {"journaled": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertEqual(event_ids, {journaled_event.id})
