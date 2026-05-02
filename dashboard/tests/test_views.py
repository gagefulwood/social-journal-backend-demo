from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import ContactFactory, UserFactory
from core.constants import (
    RELATIONSHIP_TREND_DORMANT,
    RELATIONSHIP_TREND_FADING,
    RELATIONSHIP_TREND_GROWING,
    RELATIONSHIP_TREND_STABLE,
)
from events.models import Event, EventParticipant


class DashboardDecayRadarTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def _event_for_contact(self, contact, days_ago):
        event = Event.objects.create(
            user=self.user,
            title=f"Event for {contact.first_name}",
            event_timestamp=timezone.now() - timedelta(days=days_ago),
        )
        EventParticipant.objects.create(event=event, contact=contact)
        return event

    def _contact_with_event(self, first_name, trend, strength, days_ago):
        contact = ContactFactory(user=self.user, first_name=first_name, last_name="")
        event = self._event_for_contact(contact, days_ago)
        contact.relationship_trend = trend
        contact.connection_strength = strength
        contact.save(update_fields=["relationship_trend", "connection_strength"])
        return contact, event

    def test_decay_radar_uses_relationship_trend_and_flat_shape(self):
        fading, fading_event = self._contact_with_event(
            "Fading",
            RELATIONSHIP_TREND_FADING,
            60,
            35,
        )
        dormant, _ = self._contact_with_event(
            "Dormant",
            RELATIONSHIP_TREND_DORMANT,
            90,
            50,
        )
        self._contact_with_event("Growing", RELATIONSHIP_TREND_GROWING, 100, 60)
        self._contact_with_event("Stable", RELATIONSHIP_TREND_STABLE, 80, 60)
        ContactFactory(
            user=self.user,
            first_name="Never",
            last_name="",
            relationship_trend=RELATIONSHIP_TREND_DORMANT,
            connection_strength=100,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        radar = response.data["decay_radar"]
        self.assertEqual([item["contact_id"] for item in radar], [dormant.id, fading.id])

        fading_item = next(item for item in radar if item["contact_id"] == fading.id)
        self.assertEqual(fading_item["name"], "Fading")
        self.assertEqual(fading_item["relationship_trend"], RELATIONSHIP_TREND_FADING)
        self.assertEqual(fading_item["connection_strength"], 60)
        self.assertEqual(fading_item["days_since"], 35)
        self.assertIn(fading_event.event_timestamp.date().isoformat(), fading_item["last_interaction_date"])
        self.assertNotIn("contact", fading_item)
        self.assertNotIn("days_since_interaction", fading_item)

    def test_decay_radar_caps_at_ten_items(self):
        expected_ids = []
        for index in range(12):
            contact, _ = self._contact_with_event(
                f"Contact{index}",
                RELATIONSHIP_TREND_FADING,
                index,
                30 + index,
            )
            if index >= 2:
                expected_ids.append(contact.id)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        radar = response.data["decay_radar"]
        self.assertEqual(len(radar), 10)
        self.assertEqual(
            [item["contact_id"] for item in radar],
            list(reversed(expected_ids)),
        )
