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
from journals.models import Exercise, Log, Reflection
from lookups.models import ContextCategory


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


class DashboardMVPWidgetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def _event(self, days_offset, **kwargs):
        timestamp = timezone.now() + timedelta(days=days_offset)
        defaults = {
            "user": self.user,
            "title": f"Event {days_offset}",
            "event_timestamp": timestamp,
        }
        defaults.update(kwargs)
        return Event.objects.create(**defaults)

    def _set_created_date(self, entry, days_ago):
        created_timestamp = timezone.now() - timedelta(days=days_ago)
        entry.__class__.objects.filter(pk=entry.pk).update(
            created_timestamp=created_timestamp,
        )

    def test_interaction_heatmap_defaults_to_365_days_and_includes_zero_days(self):
        today = timezone.localdate()
        event_today = self._event(0)
        Event.objects.create(
            user=self.user,
            title="Yesterday",
            event_timestamp=timezone.now() - timedelta(days=1),
        )
        Event.objects.create(
            user=self.other_user,
            title="Other",
            event_timestamp=timezone.now(),
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        heatmap = response.data["interaction_heatmap"]
        self.assertEqual(len(heatmap), 365)
        self.assertEqual(heatmap[-1]["date"], today.isoformat())
        today_item = next(item for item in heatmap if item["date"] == today.isoformat())
        self.assertEqual(today_item["count"], 1)
        self.assertTrue(any(item["count"] == 0 for item in heatmap))
        self.assertEqual(event_today.user, self.user)

    def test_interaction_heatmap_accepts_positive_window(self):
        response = self.client.get(reverse("dashboard"), {"heatmap_window": "7"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["interaction_heatmap"]), 7)

    def test_interaction_heatmap_rejects_invalid_window(self):
        response = self.client.get(reverse("dashboard"), {"heatmap_window": "0"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("heatmap_window", response.data)

    def test_activity_stats_include_required_entry_event_and_streak_counts(self):
        today_event = self._event(0)
        yesterday_event = self._event(-1)
        old_event = self._event(-40)
        Log.objects.create(user=self.user, event=today_event, title="Today", body="Body")
        yesterday_log = Log.objects.create(
            user=self.user,
            event=yesterday_event,
            title="Yesterday",
            body="Body",
        )
        reflection = Reflection.objects.create(
            user=self.user,
            event=today_event,
            clarity_check="Clear",
        )
        old_exercise = Exercise.objects.create(
            user=self.user,
            event=old_event,
            pre_measurement=1,
            post_measurement=2,
        )
        self._set_created_date(yesterday_log, 1)
        self._set_created_date(old_exercise, 40)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stats = response.data["activity_stats"]
        self.assertEqual(stats["entries_total"], 4)
        self.assertEqual(stats["entries_30d"], 3)
        self.assertEqual(
            stats["entries_by_kind_30d"],
            {"log": 2, "reflection": 1, "exercise": 0},
        )
        self.assertEqual(stats["events_30d"], 2)
        self.assertEqual(stats["current_streak_days"], 2)
        self.assertEqual(reflection.user, self.user)

    def test_current_streak_is_zero_without_entry_today(self):
        yesterday_event = self._event(-1)
        yesterday_log = Log.objects.create(
            user=self.user,
            event=yesterday_event,
            title="Yesterday",
            body="Body",
        )
        self._set_created_date(yesterday_log, 1)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["activity_stats"]["current_streak_days"], 0)

    def test_upcoming_and_recent_events_use_required_shape_and_limits(self):
        category = ContextCategory.objects.create(
            user=self.user,
            name="Social",
            color="#000000",
        )
        contact = ContactFactory(user=self.user)
        upcoming_events = [
            self._event(index + 1, tier="milestone", context_category=category)
            for index in range(6)
        ]
        recent_events = [
            self._event(-(index + 1), tier="routine", context_category=category)
            for index in range(6)
        ]
        self._event(-40)
        EventParticipant.objects.create(event=upcoming_events[0], contact=contact)
        Log.objects.create(
            user=self.user,
            event=recent_events[0],
            title="Recent Log",
            body="Body",
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        upcoming = response.data["upcoming_events"]
        recent = response.data["recent_events"]
        self.assertEqual(len(upcoming), 5)
        self.assertEqual(len(recent), 5)
        self.assertEqual(
            [event["id"] for event in upcoming],
            [event.id for event in upcoming_events[:5]],
        )
        self.assertEqual(
            [event["id"] for event in recent],
            [event.id for event in recent_events[:5]],
        )
        self.assertEqual(upcoming[0]["tier"], "milestone")
        self.assertEqual(upcoming[0]["participant_count"], 1)
        self.assertIn("context_category", upcoming[0])
        self.assertTrue(recent[0]["journaled"])
