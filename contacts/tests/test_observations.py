from importlib import import_module

from django.apps import apps
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from contacts.models import (
    OBSERVATION_STATUS_ARCHIVED,
    OBSERVATION_STATUS_CURRENT,
    OBSERVATION_STATUS_REVISIT_LATER,
    OBSERVATION_TYPE_CHANGE,
    OBSERVATION_TYPE_CHOICES,
    OBSERVATION_TYPE_NOTICE,
    Observation,
)
from events.models import EventParticipant
from events.tests.factories import EventFactory
from lookups.models import ObservationMarker

from .factories import ContactFactory, ObservationFactory, UserFactory


class ObservationModelTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.contact = ContactFactory(
            user=self.user,
            first_name="Ada",
            last_name="Lovelace",
        )
        self.marker = ObservationMarker.objects.create(
            user=self.user,
            name="Important",
            color_hex="#E53E3E",
            icon_reference="FiAlertCircle",
        )

    def test_str_returns_observation_contact_and_date(self):
        observation = Observation.objects.create(
            contact=self.contact,
            marker=self.marker,
            body="Seemed tired after lunch.",
        )

        self.assertEqual(
            str(observation),
            f"Observation for Ada Lovelace - {observation.created_timestamp:%Y-%m-%d}",
        )

    def test_db_table_is_observations(self):
        self.assertEqual(Observation._meta.db_table, "observations")

    def test_new_lifecycle_fields_default_to_current(self):
        observation = Observation.objects.create(
            contact=self.contact,
            marker=self.marker,
            body="Seemed tired after lunch.",
        )

        self.assertIsNone(observation.observation_type)
        self.assertEqual(observation.status, OBSERVATION_STATUS_CURRENT)
        self.assertTrue(observation.is_active)
        self.assertIsNone(observation.occurred_at)
        self.assertIsNone(observation.event)
        self.assertIsNone(observation.archived_at)

    def test_lifecycle_status_synchronizes_legacy_active_and_archive_fields(self):
        observation = Observation.objects.create(
            contact=self.contact,
            body="Follow up later.",
            observation_type=OBSERVATION_TYPE_CHANGE,
        )
        observation.status = OBSERVATION_STATUS_ARCHIVED
        observation.save(update_fields=["status"])
        observation.refresh_from_db()

        self.assertFalse(observation.is_active)
        self.assertIsNotNone(observation.archived_at)

        observation.status = OBSERVATION_STATUS_REVISIT_LATER
        observation.save(update_fields=["status"])
        observation.refresh_from_db()

        self.assertTrue(observation.is_active)
        self.assertIsNone(observation.archived_at)

    def test_status_is_authoritative_over_legacy_is_active_writes(self):
        observation = Observation.objects.create(
            contact=self.contact,
            body="Still current.",
            is_active=False,
        )

        self.assertEqual(observation.status, OBSERVATION_STATUS_CURRENT)
        self.assertTrue(observation.is_active)

    def test_observation_type_choices_include_approved_values(self):
        self.assertEqual(
            set(dict(OBSERVATION_TYPE_CHOICES)),
            {"notice", "conversation_cue", "appreciation", "change"},
        )

    def test_status_backfill_uses_legacy_active_without_inventing_timestamps(self):
        active_observation = Observation.objects.create(
            contact=self.contact,
            body="Current legacy observation.",
        )
        archived_observation = Observation.objects.create(
            contact=self.contact,
            body="Archived legacy observation.",
        )
        Observation.objects.filter(pk=active_observation.pk).update(
            is_active=True,
            status=OBSERVATION_STATUS_ARCHIVED,
            archived_at=None,
        )
        Observation.objects.filter(pk=archived_observation.pk).update(
            is_active=False,
            status=OBSERVATION_STATUS_CURRENT,
            archived_at=None,
        )

        migration = import_module(
            "contacts.migrations.0012_observation_context_lifecycle"
        )
        migration.backfill_observation_status(apps, None)

        active_observation.refresh_from_db()
        archived_observation.refresh_from_db()
        self.assertEqual(active_observation.status, OBSERVATION_STATUS_CURRENT)
        self.assertEqual(archived_observation.status, OBSERVATION_STATUS_ARCHIVED)
        self.assertIsNone(active_observation.archived_at)
        self.assertIsNone(archived_observation.archived_at)

    def test_contact_observations_reverse_accessor_returns_observations(self):
        observation = ObservationFactory(contact=self.contact, marker=self.marker)

        self.assertEqual(list(self.contact.observations.all()), [observation])

    def test_observation_marker_observations_reverse_accessor_returns_observations(self):
        observation = ObservationFactory(contact=self.contact, marker=self.marker)

        self.assertEqual(list(self.marker.observations.all()), [observation])


class ObservationManagerTests(TestCase):
    def test_for_user_returns_only_observations_for_owned_contacts(self):
        user = UserFactory()
        other_user = UserFactory()
        owned_contact = ContactFactory(user=user)
        other_contact = ContactFactory(user=other_user)
        owned_observation = ObservationFactory(contact=owned_contact)
        ObservationFactory(contact=other_contact)

        observations = Observation.objects.for_user(user)

        self.assertEqual(list(observations), [owned_observation])

    def test_for_user_returns_empty_queryset_for_user_without_contact_observations(self):
        user = UserFactory()
        ObservationFactory()

        observations = Observation.objects.for_user(user)

        self.assertEqual(list(observations), [])

    def test_for_user_excludes_observations_for_inactive_contacts(self):
        user = UserFactory()
        active_contact = ContactFactory(user=user, is_active=True)
        inactive_contact = ContactFactory(user=user, is_active=False)
        active_observation = ObservationFactory(contact=active_contact)
        ObservationFactory(contact=inactive_contact)

        observations = Observation.objects.for_user(user)

        self.assertEqual(list(observations), [active_observation])


class ObservationViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.contact = ContactFactory(user=self.user)
        self.other_contact = ContactFactory(user=self.other_user)
        self.marker = ObservationMarker.objects.create(
            user=self.user,
            name="Important",
            color_hex="#E53E3E",
            icon_reference="FiAlertCircle",
        )
        self.other_marker = ObservationMarker.objects.create(
            user=self.user,
            name="Low priority",
            color_hex="#3182CE",
            icon_reference="FiInfo",
        )
        self.other_users_marker = ObservationMarker.objects.create(
            user=self.other_user,
            name="Private marker",
            color_hex="#4A5568",
        )
        self.client.force_authenticate(user=self.user)

    def test_list_returns_observations_for_contact_owner(self):
        observation = ObservationFactory(
            contact=self.contact,
            marker=self.marker,
            body="Seemed tired after lunch.",
        )
        ObservationFactory(contact=self.other_contact)

        response = self.client.get(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], observation.id)

    def test_create_observation_sets_contact_from_url(self):
        response = self.client.post(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id}),
            {
                "contact": self.other_contact.id,
                "marker": self.marker.id,
                "body": "Seemed tired after lunch.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        observation = Observation.objects.get(id=response.data["id"])
        self.assertEqual(observation.marker, self.marker)
        self.assertEqual(observation.contact, self.contact)

    def test_create_observation_allows_event_shared_with_contact(self):
        event = EventFactory(user=self.user, title="Shared coffee")
        EventParticipant.objects.create(event=event, contact=self.contact)

        response = self.client.post(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id}),
            {"body": "They mentioned a new project.", "event": event.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["event"], event.id)
        self.assertEqual(response.data["event_summary"]["id"], event.id)
        self.assertEqual(response.data["event_summary"]["title"], "Shared coffee")

    def test_create_rejects_another_users_event(self):
        other_event = EventFactory(user=self.other_user)

        response = self.client.post(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id}),
            {"body": "Private event injection.", "event": other_event.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("event", response.data)

    def test_create_rejects_same_user_event_without_contact_participant(self):
        event = EventFactory(user=self.user)

        response = self.client.post(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id}),
            {"body": "Unshared event.", "event": event.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("event", response.data)

    def test_event_deletion_preserves_observation_and_clears_event(self):
        event = EventFactory(user=self.user)
        EventParticipant.objects.create(event=event, contact=self.contact)
        observation = Observation.objects.create(
            contact=self.contact,
            body="A linked observation.",
            event=event,
        )

        event.delete()
        observation.refresh_from_db()

        self.assertIsNone(observation.event)

    def test_observation_represents_a_null_event_without_summary(self):
        observation = Observation.objects.create(
            contact=self.contact,
            body="An unlinked observation.",
        )

        response = self.client.get(
            reverse("contact-observations-detail", kwargs={
                "contact_pk": self.contact.id,
                "pk": observation.id,
            })
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["event"])
        self.assertIsNone(response.data["event_summary"])

    def test_create_rejects_another_users_observation_marker(self):
        response = self.client.post(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id}),
            {
                "marker": self.other_users_marker.id,
                "body": "Private marker injection.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("marker", response.data)

    def test_other_users_contact_is_inaccessible(self):
        response = self.client.get(
            reverse(
                "contact-observations-list",
                kwargs={"contact_pk": self.other_contact.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_contact_is_inaccessible_for_list_and_create(self):
        self.contact.is_active = False
        self.contact.save(update_fields=["is_active"])
        url = reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id})

        list_response = self.client.get(url)
        create_response = self.client.post(
            url,
            {"marker": self.marker.id, "body": "Should not save."},
            format="json",
        )

        self.assertEqual(list_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(create_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_marker(self):
        matching_observation = ObservationFactory(
            contact=self.contact,
            marker=self.marker,
        )
        ObservationFactory(contact=self.contact, marker=self.other_marker)

        response = self.client.get(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id}),
            {"marker": self.marker.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], matching_observation.id)

    def test_filter_by_is_active(self):
        active_observation = ObservationFactory(contact=self.contact, is_active=True)
        archived_observation = ObservationFactory(
            contact=self.contact,
            status=OBSERVATION_STATUS_ARCHIVED,
        )
        url = reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id})

        active_response = self.client.get(url, {"is_active": "true"})
        archived_response = self.client.get(url, {"is_active": "false"})

        self.assertEqual(active_response.status_code, status.HTTP_200_OK)
        self.assertEqual(active_response.data["count"], 1)
        self.assertEqual(active_response.data["results"][0]["id"], active_observation.id)
        self.assertEqual(archived_response.status_code, status.HTTP_200_OK)
        self.assertEqual(archived_response.data["count"], 1)
        self.assertEqual(archived_response.data["results"][0]["id"], archived_observation.id)

    def test_status_is_the_only_writable_lifecycle_field(self):
        response = self.client.post(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id}),
            {
                "body": "Archive this later.",
                "status": OBSERVATION_STATUS_ARCHIVED,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], OBSERVATION_STATUS_ARCHIVED)
        self.assertFalse(response.data["is_active"])
        self.assertIsNotNone(response.data["archived_at"])

        response = self.client.patch(
            reverse("contact-observations-detail", kwargs={
                "contact_pk": self.contact.id,
                "pk": response.data["id"],
            }),
            {
                "status": OBSERVATION_STATUS_REVISIT_LATER,
                "archived_at": "2026-01-01T00:00:00Z",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OBSERVATION_STATUS_REVISIT_LATER)
        self.assertTrue(response.data["is_active"])
        self.assertIsNone(response.data["archived_at"])

    def test_archived_observation_can_be_restored_through_its_detail_route(self):
        observation = Observation.objects.create(
            contact=self.contact,
            body="Restore this observation.",
            status=OBSERVATION_STATUS_ARCHIVED,
        )

        response = self.client.patch(
            reverse("contact-observations-detail", kwargs={
                "contact_pk": self.contact.id,
                "pk": observation.id,
            }),
            {"status": OBSERVATION_STATUS_CURRENT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OBSERVATION_STATUS_CURRENT)
        self.assertTrue(response.data["is_active"])
        self.assertIsNone(response.data["archived_at"])

    def test_default_list_hides_archived_observations_and_status_returns_history(self):
        current = ObservationFactory(
            contact=self.contact,
            status=OBSERVATION_STATUS_CURRENT,
        )
        revisit = ObservationFactory(
            contact=self.contact,
            status=OBSERVATION_STATUS_REVISIT_LATER,
        )
        archived = ObservationFactory(
            contact=self.contact,
            status=OBSERVATION_STATUS_ARCHIVED,
        )
        url = reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id})

        default_response = self.client.get(url)
        archived_response = self.client.get(url, {"status": OBSERVATION_STATUS_ARCHIVED})

        self.assertEqual(
            {item["id"] for item in default_response.data["results"]},
            {current.id, revisit.id},
        )
        self.assertEqual(archived_response.data["count"], 1)
        self.assertEqual(archived_response.data["results"][0]["id"], archived.id)

    def test_filters_search_type_event_and_date_ranges(self):
        event = EventFactory(user=self.user)
        EventParticipant.objects.create(event=event, contact=self.contact)
        occurred_at = timezone.now() - timezone.timedelta(days=2)
        matching_observation = Observation.objects.create(
            contact=self.contact,
            body="Remember the oat milk preference.",
            marker=self.marker,
            observation_type=OBSERVATION_TYPE_NOTICE,
            occurred_at=occurred_at,
            event=event,
        )
        ObservationFactory(contact=self.contact, body="Unrelated observation.")
        url = reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id})

        responses = [
            self.client.get(url, {"search": "oat milk"}),
            self.client.get(url, {"observation_type": OBSERVATION_TYPE_NOTICE}),
            self.client.get(url, {"marker": self.marker.id}),
            self.client.get(url, {"event": event.id}),
            self.client.get(
                url,
                {"occurred_after": (occurred_at - timezone.timedelta(hours=1)).isoformat()},
            ),
        ]

        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(response.data["results"][0]["id"], matching_observation.id)

    def test_filters_created_date_ranges(self):
        now = timezone.now()
        matching_observation = ObservationFactory(contact=self.contact)
        other_observation = ObservationFactory(contact=self.contact)
        Observation.objects.filter(pk=matching_observation.pk).update(
            created_timestamp=now - timezone.timedelta(days=2),
        )
        Observation.objects.filter(pk=other_observation.pk).update(
            created_timestamp=now - timezone.timedelta(days=5),
        )
        url = reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id})

        after_response = self.client.get(
            url,
            {"created_after": (now - timezone.timedelta(days=3)).isoformat()},
        )
        before_response = self.client.get(
            url,
            {"created_before": (now - timezone.timedelta(days=3)).isoformat()},
        )

        self.assertEqual(after_response.data["count"], 1)
        self.assertEqual(after_response.data["results"][0]["id"], matching_observation.id)
        self.assertEqual(before_response.data["count"], 1)
        self.assertEqual(before_response.data["results"][0]["id"], other_observation.id)

    def test_list_orders_by_meaningful_timestamp_with_primary_key_tie_breaker(self):
        now = timezone.now()
        oldest = Observation.objects.create(
            contact=self.contact,
            body="Oldest.",
            occurred_at=now - timezone.timedelta(days=3),
        )
        fallback = Observation.objects.create(
            contact=self.contact,
            body="Fallback.",
        )
        newest = Observation.objects.create(
            contact=self.contact,
            body="Newest.",
            occurred_at=now - timezone.timedelta(days=1),
        )
        Observation.objects.filter(pk=fallback.pk).update(
            created_timestamp=now - timezone.timedelta(days=2),
        )

        response = self.client.get(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id})
        )

        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [newest.id, fallback.id, oldest.id],
        )

    def test_pagination_is_stable_when_meaningful_timestamps_match(self):
        occurred_at = timezone.now()
        observations = [
            Observation.objects.create(
                contact=self.contact,
                body=f"Observation {index}",
                occurred_at=occurred_at,
            )
            for index in range(21)
        ]
        url = reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id})

        first_page = self.client.get(url)
        second_page = self.client.get(url, {"page": 2})

        expected_ids = [observation.id for observation in reversed(observations)]
        self.assertEqual(
            [item["id"] for item in first_page.data["results"]],
            expected_ids[:20],
        )
        self.assertEqual(
            [item["id"] for item in second_page.data["results"]],
            expected_ids[20:],
        )

    def test_list_uses_loaded_marker_and_event_relations(self):
        event = EventFactory(user=self.user)
        EventParticipant.objects.create(event=event, contact=self.contact)
        Observation.objects.create(
            contact=self.contact,
            marker=self.marker,
            body="A linked observation.",
            event=event,
        )

        with self.assertNumQueries(3):
            response = self.client.get(
                reverse(
                    "contact-observations-list",
                    kwargs={"contact_pk": self.contact.id},
                )
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_old_contact_notes_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("contact-notes-list", kwargs={"contact_pk": self.contact.id})

    def test_old_contact_notes_path_is_removed(self):
        response = self.client.get(f"/api/contacts/{self.contact.id}/notes/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
