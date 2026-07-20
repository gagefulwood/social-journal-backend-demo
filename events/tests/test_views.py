from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import ContactFactory, UserFactory
from events.models import Event, EventParticipant
from events.views import EventViewSet
from journals.models import Log, Reflection
from lookups.models import (
    ContextCategory,
    InteractionMode,
    MediaType,
    Mood,
    Occupation,
    Relation,
)
from media.models import MediaAsset

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

    def test_list_and_retrieve_omit_inactive_contact_participants(self):
        event = EventFactory(user=self.user)
        active_contact = ContactFactory(user=self.user)
        inactive_contact = ContactFactory(user=self.user)
        inactive_contact.is_active = False
        inactive_contact.save(update_fields=["is_active"])
        EventParticipant.objects.create(event=event, contact=active_contact)
        EventParticipant.objects.create(event=event, contact=inactive_contact)

        list_response = self.client.get(reverse("event-list"))
        detail_response = self.client.get(
            reverse("event-detail", args=[event.id]),
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        list_event = list_response.data["results"][0]
        self.assertEqual(
            [participant["contact"]["id"] for participant in list_event["participants"]],
            [active_contact.id],
        )
        self.assertEqual(list_event["participant_count"], 1)
        self.assertEqual(
            [
                participant["contact"]["id"]
                for participant in detail_response.data["participants"]
            ],
            [active_contact.id],
        )

    def test_list_and_retrieve_omit_cross_owner_participant_joins(self):
        event = EventFactory(user=self.user)
        owned_contact = ContactFactory(user=self.user)
        other_contact = ContactFactory(user=self.other_user)
        EventParticipant.objects.create(event=event, contact=owned_contact)
        EventParticipant.objects.create(event=event, contact=other_contact)

        list_response = self.client.get(reverse("event-list"))
        detail_response = self.client.get(
            reverse("event-detail", args=[event.id]),
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        list_event = list_response.data["results"][0]
        self.assertEqual(
            [participant["contact"]["id"] for participant in list_event["participants"]],
            [owned_contact.id],
        )
        self.assertEqual(list_event["participant_count"], 1)
        self.assertEqual(
            [
                participant["contact"]["id"]
                for participant in detail_response.data["participants"]
            ],
            [owned_contact.id],
        )

        search_response = self.client.get(
            reverse("event-list"),
            {"search": other_contact.first_name},
        )
        participant_filter_response = self.client.get(
            reverse("event-list"),
            {"participants": str(other_contact.id)},
        )

        self.assertEqual(search_response.status_code, status.HTTP_200_OK)
        self.assertEqual(search_response.data["count"], 0)
        self.assertEqual(
            participant_filter_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(participant_filter_response.data["count"], 0)

    def test_event_participants_suppress_inactive_profile_media(self):
        profile_picture = MediaAsset.objects.create(
            user=self.user,
            file="media/inactive-profile.png",
            original_filename="inactive-profile.png",
            content_type="image/png",
            is_active=False,
        )
        contact = ContactFactory(
            user=self.user,
            profile_picture=profile_picture,
        )
        event = EventFactory(user=self.user)
        EventParticipant.objects.create(event=event, contact=contact)

        list_response = self.client.get(reverse("event-list"))
        detail_response = self.client.get(
            reverse("event-detail", args=[event.id]),
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(
            list_response.data["results"][0]["participants"][0]["contact"][
                "profile_picture"
            ]
        )
        self.assertIsNone(
            detail_response.data["participants"][0]["contact"]["profile_picture"]
        )

    def test_list_default_order_is_deterministic_across_pages(self):
        shared_timestamp = timezone.now()
        events = [
            EventFactory(
                user=self.user,
                title=f"Same time {index}",
                event_timestamp=shared_timestamp,
            )
            for index in range(5)
        ]

        responses = [
            self.client.get(
                reverse("event-list"),
                {"page": page, "page_size": 2},
            )
            for page in (1, 2, 3)
        ]

        self.assertTrue(
            all(
                response.status_code == status.HTTP_200_OK
                for response in responses
            )
        )
        returned_ids = [
            event["id"]
            for response in responses
            for event in response.data["results"]
        ]
        self.assertEqual(returned_ids, [event.id for event in reversed(events)])

    def test_create_sets_user_and_participants_from_request(self):
        contact = ContactFactory(user=self.user)
        interaction_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )
        mood = Mood.objects.create(name="Happy", emoji_icon="H", is_system_default=True)

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Dinner",
                "description": "Caught up over dinner.",
                "event_timestamp": timezone.now().isoformat(),
                "user": self.other_user.id,
                "end_timestamp": (timezone.now() + timedelta(hours=2)).isoformat(),
                "location_label": "Cafe",
                "tier": "milestone",
                "impact": "positive",
                "interaction_mode_id": interaction_mode.id,
                "mood_id": mood.id,
                "participants": [contact.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(id=response.data["id"])
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.description, "Caught up over dinner.")
        self.assertEqual(event.location_label, "Cafe")
        self.assertEqual(event.tier, "milestone")
        self.assertEqual(event.impact, "positive")
        self.assertEqual(event.interaction_mode, interaction_mode)
        self.assertEqual(event.mood, mood)
        self.assertEqual(response.data["mood"]["id"], mood.id)
        self.assertTrue(
            EventParticipant.objects.filter(event=event, contact=contact).exists()
        )

    def test_create_deduplicates_repeated_participant_ids(self):
        contact = ContactFactory(user=self.user)

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Dinner",
                "event_timestamp": timezone.now().isoformat(),
                "participants": [contact.id, contact.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(pk=response.data["id"])
        self.assertEqual(
            EventParticipant.objects.filter(event=event, contact=contact).count(),
            1,
        )
        self.assertEqual(len(response.data["participants"]), 1)

    def test_create_rejects_inactive_participant(self):
        contact = ContactFactory(user=self.user)
        contact.is_active = False
        contact.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Dinner",
                "event_timestamp": timezone.now().isoformat(),
                "participants": [contact.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("participants", response.data)
        self.assertFalse(Event.objects.filter(title="Dinner").exists())

    def test_participant_validation_does_not_reveal_cross_owner_existence(self):
        contact = ContactFactory(user=self.other_user)
        payload = {
            "title": "Dinner",
            "event_timestamp": timezone.now().isoformat(),
            "participants": [contact.id],
        }

        existing_response = self.client.post(
            reverse("event-list"),
            payload,
            format="json",
        )
        contact.delete()
        missing_response = self.client.post(
            reverse("event-list"),
            payload,
            format="json",
        )

        self.assertEqual(existing_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(existing_response.data, missing_response.data)

    def test_create_rolls_back_event_when_participant_write_fails(self):
        contact = ContactFactory(user=self.user)

        with patch(
            "events.serializers.EventParticipant.objects.create",
            side_effect=RuntimeError("participant write failed"),
        ):
            with self.assertRaisesMessage(RuntimeError, "participant write failed"):
                self.client.post(
                    reverse("event-list"),
                    {
                        "title": "Atomic dinner",
                        "event_timestamp": timezone.now().isoformat(),
                        "participants": [contact.id],
                    },
                    format="json",
                )

        self.assertFalse(Event.objects.filter(title="Atomic dinner").exists())

    def test_create_accepts_owner_visible_context_categories(self):
        system_category = ContextCategory.objects.create(
            name="System context",
            color="#111111",
            is_system_default=True,
        )
        owner_category = ContextCategory.objects.create(
            user=self.user,
            name="Owner context",
            color="#222222",
        )

        for category in (system_category, owner_category):
            with self.subTest(category=category.name):
                response = self.client.post(
                    reverse("event-list"),
                    {
                        "title": f"Event for {category.name}",
                        "event_timestamp": timezone.now().isoformat(),
                        "context_category": category.id,
                    },
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertEqual(response.data["context_category"], category.id)

    def test_create_rejects_other_users_context_category(self):
        private_category = ContextCategory.objects.create(
            user=self.other_user,
            name="Private context",
            color="#333333",
        )

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Cross-owner category",
                "event_timestamp": timezone.now().isoformat(),
                "context_category": private_category.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("context_category", response.data)
        self.assertFalse(Event.objects.filter(title="Cross-owner category").exists())

    def test_create_rejects_end_timestamp_before_event_timestamp(self):
        event_timestamp = timezone.now()

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Invalid range",
                "event_timestamp": event_timestamp.isoformat(),
                "end_timestamp": (
                    event_timestamp - timedelta(minutes=1)
                ).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_timestamp", response.data)
        self.assertFalse(Event.objects.filter(title="Invalid range").exists())

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
        self.assertEqual(journaled.data["journals"]["logs"][0]["title"], "Log")

    def test_retrieve_bounds_journal_previews_and_returns_full_counts(self):
        event = EventFactory(user=self.user)
        now = timezone.now()
        logs = []
        reflections = []
        for index in range(6):
            log = Log.objects.create(
                user=self.user,
                event=event,
                title=f"Log {index}",
            )
            reflection = Reflection.objects.create(
                user=self.user,
                event=event,
                title=f"Reflection {index}",
            )
            updated_at = now + timedelta(minutes=index)
            Log.objects.filter(pk=log.pk).update(
                created_timestamp=updated_at,
                updated_timestamp=updated_at,
            )
            Reflection.objects.filter(pk=reflection.pk).update(
                created_timestamp=updated_at,
                updated_timestamp=updated_at,
            )
            logs.append(log)
            reflections.append(reflection)

        response = self.client.get(reverse("event-detail", args=[event.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        journals = response.data["journals"]
        self.assertEqual(journals["log_count"], 6)
        self.assertEqual(journals["reflection_count"], 6)
        self.assertEqual(
            [item["id"] for item in journals["logs"]],
            [log.id for log in reversed(logs[-4:])],
        )
        self.assertEqual(
            [item["id"] for item in journals["reflections"]],
            [reflection.id for reflection in reversed(reflections[-4:])],
        )

    def test_list_queryset_does_not_prefetch_journal_collections(self):
        view = EventViewSet()
        view.action = 'list'
        view.request = SimpleNamespace(user=self.user)

        queryset = view.get_queryset()

        prefetch_targets = {
            getattr(item, 'prefetch_through', item)
            for item in queryset._prefetch_related_lookups
        }
        self.assertEqual(prefetch_targets, {'participants'})
        self.assertIn('journal_log_exists', queryset.query.annotations)
        self.assertIn('journal_reflection_exists', queryset.query.annotations)

    def test_related_returns_404_for_other_users_event(self):
        other_event = EventFactory(user=self.other_user)

        response = self.client.get(reverse("event-related", args=[other_event.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_related_excludes_base_event_and_other_users_events(self):
        category = ContextCategory.objects.create(
            user=self.user,
            name="Related Social",
            color="#000000",
        )
        base_event = EventFactory(
            user=self.user,
            context_category=category,
            tier="milestone",
        )
        owned_related = EventFactory(
            user=self.user,
            context_category=category,
            tier="milestone",
        )
        EventFactory(
            user=self.other_user,
            context_category=category,
            tier="milestone",
        )

        response = self.client.get(reverse("event-related", args=[base_event.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([event["id"] for event in response.data], [owned_related.id])

    def test_related_ranks_by_pinned_reason_weights(self):
        now = timezone.now()
        category = ContextCategory.objects.create(
            user=self.user,
            name="Social",
            color="#000000",
        )
        other_category = ContextCategory.objects.create(
            user=self.user,
            name="Errands",
            color="#111111",
        )
        interaction_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )
        other_mode = InteractionMode.objects.create(
            name="Video call",
            is_system_default=True,
        )
        contact = ContactFactory(user=self.user)
        base_event = EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=10),
            context_category=category,
            interaction_mode=interaction_mode,
            tier="milestone",
        )
        EventParticipant.objects.create(event=base_event, contact=contact)
        shared_participant = EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=20),
            context_category=other_category,
            interaction_mode=other_mode,
            tier="routine",
        )
        EventParticipant.objects.create(event=shared_participant, contact=contact)
        same_context = EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=1),
            context_category=category,
            interaction_mode=other_mode,
            tier="routine",
        )
        same_mode = EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=2),
            context_category=other_category,
            interaction_mode=interaction_mode,
            tier="routine",
        )
        same_tier = EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=3),
            context_category=other_category,
            interaction_mode=other_mode,
            tier="milestone",
        )

        response = self.client.get(
            reverse("event-related", args=[base_event.id]),
            {"limit": 10},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [event["id"] for event in response.data],
            [
                shared_participant.id,
                same_context.id,
                same_mode.id,
                same_tier.id,
            ],
        )
        self.assertEqual(
            [event["relation_reasons"] for event in response.data],
            [
                ["shared_participant"],
                ["same_context"],
                ["same_interaction_mode"],
                ["same_tier"],
            ],
        )

    def test_related_relation_reasons_are_highest_weight_first(self):
        category = ContextCategory.objects.create(
            user=self.user,
            name="Social",
            color="#000000",
        )
        interaction_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )
        contact = ContactFactory(user=self.user)
        base_event = EventFactory(
            user=self.user,
            context_category=category,
            interaction_mode=interaction_mode,
            tier="milestone",
        )
        EventParticipant.objects.create(event=base_event, contact=contact)
        related_event = EventFactory(
            user=self.user,
            context_category=category,
            interaction_mode=interaction_mode,
            tier="milestone",
        )
        EventParticipant.objects.create(event=related_event, contact=contact)

        response = self.client.get(reverse("event-related", args=[base_event.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data[0]["relation_reasons"],
            [
                "shared_participant",
                "same_context",
                "same_interaction_mode",
                "same_tier",
            ],
        )

    def test_related_limit_defaults_to_two_and_caps_at_ten(self):
        now = timezone.now()
        base_event = EventFactory(user=self.user, tier="routine")
        related_events = []
        for index in range(12):
            related_events.append(
                EventFactory(
                    user=self.user,
                    event_timestamp=now - timedelta(days=index),
                    tier="routine",
                )
            )

        default_response = self.client.get(
            reverse("event-related", args=[base_event.id]),
        )
        capped_response = self.client.get(
            reverse("event-related", args=[base_event.id]),
            {"limit": 50},
        )

        self.assertEqual(default_response.status_code, status.HTTP_200_OK)
        self.assertEqual(capped_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(default_response.data), 2)
        self.assertEqual(len(capped_response.data), 10)
        self.assertEqual(
            [event["id"] for event in default_response.data],
            [related_events[0].id, related_events[1].id],
        )
        self.assertNotIn(base_event.id, [event["id"] for event in capped_response.data])

    def test_related_serializes_null_mood_empty_impact_and_null_mode(self):
        mood = Mood.objects.create(
            name="Happy",
            emoji_icon="H",
            polarity=1,
            is_system_default=True,
        )
        base_event = EventFactory(user=self.user, tier="routine", mood=mood)
        EventFactory(
            user=self.user,
            tier="routine",
            mood=None,
            impact="",
            interaction_mode=None,
        )

        response = self.client.get(reverse("event-related", args=[base_event.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["mood"], None)
        self.assertEqual(response.data[0]["impact"], "")
        self.assertEqual(response.data[0]["interaction_mode"], None)
        self.assertEqual(response.data[0]["relation_reasons"], ["same_tier"])

    def test_related_nested_mood_matches_detail_shape_with_numeric_polarity(self):
        mood = Mood.objects.create(
            name="Happy",
            emoji_icon="H",
            polarity=1,
            is_system_default=True,
        )
        base_event = EventFactory(user=self.user, tier="routine")
        EventFactory(user=self.user, tier="routine", mood=mood)

        response = self.client.get(reverse("event-related", args=[base_event.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["mood"]["polarity"], 1)
        self.assertIsInstance(response.data[0]["mood"]["polarity"], int)

    def test_related_does_not_query_per_result(self):
        mood = Mood.objects.create(name="Happy", emoji_icon="H", is_system_default=True)
        interaction_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )
        category = ContextCategory.objects.create(
            user=self.user,
            name="Social",
            color="#000000",
        )
        contact = ContactFactory(user=self.user)
        base_event = EventFactory(
            user=self.user,
            context_category=category,
            interaction_mode=interaction_mode,
            mood=mood,
        )
        EventParticipant.objects.create(event=base_event, contact=contact)
        for index in range(3):
            related_event = EventFactory(
                user=self.user,
                title=f"Related {index}",
                context_category=category,
                interaction_mode=interaction_mode,
                mood=mood,
            )
            EventParticipant.objects.create(event=related_event, contact=contact)
            Log.objects.create(
                user=self.user,
                event=related_event,
                title=f"Log {index}",
                body="Body",
            )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                reverse("event-related", args=[base_event.id]),
                {"limit": 3},
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        self.assertLessEqual(len(captured), 11)

    def test_related_sorts_past_first_but_includes_upcoming(self):
        now = timezone.now()
        contact = ContactFactory(user=self.user)
        base_event = EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=10),
            tier="milestone",
        )
        EventParticipant.objects.create(event=base_event, contact=contact)
        past_event = EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=1),
            tier="milestone",
        )
        upcoming_event = EventFactory(
            user=self.user,
            event_timestamp=now + timedelta(days=1),
            tier="routine",
        )
        EventParticipant.objects.create(event=upcoming_event, contact=contact)

        response = self.client.get(
            reverse("event-related", args=[base_event.id]),
            {"limit": 10},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [event["id"] for event in response.data],
            [past_event.id, upcoming_event.id],
        )

    def test_partial_update_allows_owner(self):
        event = EventFactory(user=self.user, title="Old")
        mood = Mood.objects.create(user=self.user, name="Calm", emoji_icon="C")

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"title": "New", "mood_id": mood.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.title, "New")
        self.assertEqual(event.mood, mood)

    def test_create_rejects_other_users_lookup_rows(self):
        interaction_mode = InteractionMode.objects.create(
            user=self.other_user,
            name="Private",
        )
        mood = Mood.objects.create(
            user=self.other_user,
            name="Private mood",
            emoji_icon="P",
        )

        response = self.client.post(
            reverse("event-list"),
            {
                "title": "Dinner",
                "event_timestamp": timezone.now().isoformat(),
                "interaction_mode_id": interaction_mode.id,
                "mood_id": mood.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interaction_mode_id", response.data)

    def test_lookup_validation_does_not_reveal_cross_owner_existence(self):
        lookup_cases = (
            (
                "context_category",
                ContextCategory.objects.create(
                    user=self.other_user,
                    name="Private context",
                    color="#111111",
                ),
            ),
            (
                "interaction_mode_id",
                InteractionMode.objects.create(
                    user=self.other_user,
                    name="Private mode",
                ),
            ),
            (
                "mood_id",
                Mood.objects.create(
                    user=self.other_user,
                    name="Private mood",
                    emoji_icon="P",
                ),
            ),
        )

        for field_name, lookup in lookup_cases:
            with self.subTest(field_name=field_name):
                payload = {
                    "title": f"Event with {field_name}",
                    "event_timestamp": timezone.now().isoformat(),
                    field_name: lookup.id,
                }
                existing_response = self.client.post(
                    reverse("event-list"),
                    payload,
                    format="json",
                )
                lookup.delete()
                missing_response = self.client.post(
                    reverse("event-list"),
                    payload,
                    format="json",
                )

                self.assertEqual(
                    existing_response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(
                    missing_response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(existing_response.data, missing_response.data)

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

    def test_partial_update_rejects_other_users_context_category(self):
        owner_category = ContextCategory.objects.create(
            user=self.user,
            name="Owner context",
            color="#111111",
        )
        private_category = ContextCategory.objects.create(
            user=self.other_user,
            name="Private context",
            color="#222222",
        )
        event = EventFactory(user=self.user, context_category=owner_category)

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"context_category": private_category.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("context_category", response.data)
        event.refresh_from_db()
        self.assertEqual(event.context_category, owner_category)

    def test_partial_update_accepts_owner_visible_context_category(self):
        category = ContextCategory.objects.create(
            user=self.user,
            name="Owner context",
            color="#111111",
        )
        event = EventFactory(user=self.user)

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"context_category": category.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.context_category, category)

    def test_partial_update_context_category_recalculates_current_participants(self):
        original_category = ContextCategory.objects.create(
            user=self.user,
            name="Original context",
            color="#111111",
        )
        replacement_category = ContextCategory.objects.create(
            user=self.user,
            name="Replacement context",
            color="#222222",
        )
        event = EventFactory(
            user=self.user,
            context_category=original_category,
        )
        contacts = [ContactFactory(user=self.user) for _ in range(2)]
        for contact in contacts:
            EventParticipant.objects.create(event=event, contact=contact)

        with patch(
            "events.serializers.recalculate_contact_statistics",
        ) as recalculate:
            response = self.client.patch(
                reverse("event-detail", args=[event.id]),
                {"context_category": replacement_category.id},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {call.args[0].id for call in recalculate.call_args_list},
            {contact.id for contact in contacts},
        )

    def test_partial_update_rolls_back_event_and_participants_on_write_failure(self):
        event = EventFactory(user=self.user, title="Original")
        existing_contact = ContactFactory(user=self.user)
        added_contact = ContactFactory(user=self.user)
        EventParticipant.objects.create(event=event, contact=existing_contact)

        with patch(
            "events.serializers.EventParticipant.objects.create",
            side_effect=RuntimeError("participant write failed"),
        ):
            with self.assertRaisesMessage(RuntimeError, "participant write failed"):
                self.client.patch(
                    reverse("event-detail", args=[event.id]),
                    {
                        "title": "Changed",
                        "participants": [existing_contact.id, added_contact.id],
                    },
                    format="json",
                )

        event.refresh_from_db()
        self.assertEqual(event.title, "Original")
        self.assertEqual(
            set(
                EventParticipant.objects.filter(event=event).values_list(
                    "contact_id",
                    flat=True,
                )
            ),
            {existing_contact.id},
        )

    def test_partial_update_rejects_end_timestamp_before_event_timestamp(self):
        event = EventFactory(user=self.user)

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {
                "end_timestamp": (
                    event.event_timestamp - timedelta(minutes=1)
                ).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_timestamp", response.data)
        event.refresh_from_db()
        self.assertIsNone(event.end_timestamp)

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

    def test_partial_update_rejects_inactive_participant(self):
        event = EventFactory(user=self.user)
        contact = ContactFactory(user=self.user)
        contact.is_active = False
        contact.save(update_fields=["is_active"])

        response = self.client.patch(
            reverse("event-detail", args=[event.id]),
            {"participants": [contact.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            EventParticipant.objects.filter(event=event, contact=contact).exists()
        )

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

    def test_filter_supports_nearest_first_timestamp_ordering(self):
        now = timezone.now()
        contact = ContactFactory(user=self.user)
        nearest_event = EventFactory(
            user=self.user,
            event_timestamp=now + timedelta(days=2),
        )
        later_event = EventFactory(
            user=self.user,
            event_timestamp=now + timedelta(days=12),
        )
        EventParticipant.objects.create(event=nearest_event, contact=contact)
        EventParticipant.objects.create(event=later_event, contact=contact)
        EventFactory(
            user=self.user,
            event_timestamp=now + timedelta(days=1),
        )
        other_user_event = EventFactory(
            user=self.other_user,
            event_timestamp=now + timedelta(days=1),
        )
        EventParticipant.objects.create(
            event=other_user_event,
            contact=ContactFactory(user=self.other_user),
        )

        response = self.client.get(
            reverse("event-list"),
            {
                "event_after": now.isoformat(),
                "participants": str(contact.id),
                "ordering": "event_timestamp",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [event["id"] for event in response.data["results"]],
            [nearest_event.id, later_event.id],
        )

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

    def test_filter_by_comma_separated_participants(self):
        first_contact = ContactFactory(user=self.user)
        second_contact = ContactFactory(user=self.user)
        first_event = EventFactory(user=self.user)
        second_event = EventFactory(user=self.user)
        EventParticipant.objects.create(event=first_event, contact=first_contact)
        EventParticipant.objects.create(event=second_event, contact=second_contact)
        EventFactory(user=self.user)
        other_contact = ContactFactory(user=self.other_user)
        other_event = EventFactory(user=self.other_user)
        EventParticipant.objects.create(event=other_event, contact=other_contact)

        response = self.client.get(
            reverse("event-list"),
            {
                "participants": (
                    f"{first_contact.id}, {second_contact.id}, {other_contact.id}"
                ),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertEqual(event_ids, {first_event.id, second_event.id})

    def test_filter_rejects_malformed_participant_id(self):
        for participant_filter in (
            "not-a-contact",
            "-1",
            "9223372036854775808",
        ):
            with self.subTest(participant_filter=participant_filter):
                response = self.client.get(
                    reverse("event-list"),
                    {"participants": participant_filter},
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(
                    response.data["participants"],
                    ["Participant IDs must be comma-separated valid positive integers."],
                )

    def test_filter_rejects_mixed_valid_and_invalid_participant_ids(self):
        contact = ContactFactory(user=self.user)
        event = EventFactory(user=self.user)
        EventParticipant.objects.create(event=event, contact=contact)

        response = self.client.get(
            reverse("event-list"),
            {"participants": f"{contact.id},invalid"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["participants"],
            ["Participant IDs must be comma-separated valid positive integers."],
        )

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

    def test_filter_by_search_impact_and_interaction_mode(self):
        interaction_mode = InteractionMode.objects.create(
            name="Video call",
            is_system_default=True,
        )
        contact = ContactFactory(
            user=self.user,
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
        )
        matching_event = EventFactory(
            user=self.user,
            title="Planning",
            description="Discussed the next project.",
            location_label="Remote",
            impact="positive",
            interaction_mode=interaction_mode,
        )
        EventParticipant.objects.create(event=matching_event, contact=contact)
        EventFactory(
            user=self.user,
            title="Planning",
            impact="negative",
            interaction_mode=None,
        )

        response = self.client.get(
            reverse("event-list"),
            {
                "search": "lovelace",
                "impact": "positive",
                "interaction_mode": interaction_mode.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertEqual(event_ids, {matching_event.id})
        self.assertEqual(response.data["results"][0]["participants"][0]["contact"]["id"], contact.id)

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

    def test_filter_has_mood_uses_event_mood_not_log_mood(self):
        mood = Mood.objects.create(name="Happy", emoji_icon="H", is_system_default=True)
        event_mood = EventFactory(user=self.user, mood=mood)
        log_mood_only = EventFactory(user=self.user)
        Log.objects.create(
            user=self.user,
            event=log_mood_only,
            title="Log",
            body="Body",
            mood=mood,
        )

        response = self.client.get(reverse("event-list"), {"has_mood": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertEqual(event_ids, {event_mood.id})

    def test_list_expanded_timeline_fields_do_not_query_per_event(self):
        mood = Mood.objects.create(name="Happy", emoji_icon="H", is_system_default=True)
        interaction_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )
        contact = ContactFactory(user=self.user)
        for index in range(3):
            event = EventFactory(
                user=self.user,
                title=f"Event {index}",
                interaction_mode=interaction_mode,
                mood=mood,
            )
            EventParticipant.objects.create(event=event, contact=contact)
            Log.objects.create(
                user=self.user,
                event=event,
                title=f"Log {index}",
                body="Body",
            )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("event-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 3)
        self.assertLessEqual(len(captured), 10)

    def test_list_participant_metadata_does_not_query_per_contact(self):
        relation = Relation.objects.create(
            user=self.user,
            name="Friend",
        )
        occupation = Occupation.objects.create(
            user=self.user,
            name="Designer",
        )
        media_type = MediaType.objects.create(
            name="EVENT_TEST_IMAGE",
            is_system_default=True,
        )
        contacts = []
        for index in range(6):
            profile_picture = MediaAsset.objects.create(
                user=self.user,
                file=f"media/event-contact-{index}.png",
                media_type=media_type,
                original_filename=f"event-contact-{index}.png",
                content_type="image/png",
            )
            contact = ContactFactory(
                user=self.user,
                relation=relation,
                occupation=occupation,
                profile_picture=profile_picture,
            )
            contacts.append(contact)
            event = EventFactory(user=self.user, title=f"Metadata event {index}")
            EventParticipant.objects.create(event=event, contact=contact)

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("event-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 6)
        self.assertLessEqual(len(captured), 6)
        rendered_contacts = [
            event["participants"][0]["contact"]
            for event in response.data["results"]
        ]
        self.assertEqual(
            {contact["id"] for contact in rendered_contacts},
            {contact.id for contact in contacts},
        )
        self.assertTrue(
            all(contact["relation_name"] == "Friend" for contact in rendered_contacts)
        )
        self.assertTrue(
            all(
                contact["occupation_name"] == "Designer"
                for contact in rendered_contacts
            )
        )
        self.assertTrue(
            all(contact["profile_picture"] for contact in rendered_contacts)
        )

    def test_timeline_summary_counts_filtered_queryset(self):
        now = timezone.now()
        mood = Mood.objects.create(name="Happy", emoji_icon="H", is_system_default=True)
        interaction_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )
        contact = ContactFactory(user=self.user)
        matching_event = EventFactory(
            user=self.user,
            event_timestamp=now + timedelta(days=1),
            tier="milestone",
            impact="positive",
            interaction_mode=interaction_mode,
            mood=mood,
        )
        EventParticipant.objects.create(event=matching_event, contact=contact)
        EventFactory(
            user=self.user,
            event_timestamp=now - timedelta(days=40),
            tier="routine",
            interaction_mode=interaction_mode,
        )
        EventFactory(
            user=self.other_user,
            event_timestamp=now + timedelta(days=1),
            tier="milestone",
            impact="positive",
            interaction_mode=interaction_mode,
            mood=mood,
        )

        response = self.client.get(
            reverse("event-timeline-summary"),
            {
                "participants": str(contact.id),
                "interaction_mode": interaction_mode.id,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_moments"], 1)
        self.assertEqual(response.data["upcoming"], 1)
        self.assertEqual(response.data["routine"], 0)
        self.assertEqual(response.data["milestone"], 1)
        self.assertEqual(response.data["this_month"], 1)
        self.assertEqual(response.data["with_mood"], 1)
        self.assertEqual(response.data["with_impact"], 1)
