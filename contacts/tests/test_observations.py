from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APIClient

from contacts.models import Observation
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
        ObservationFactory(contact=self.contact, is_active=False)

        response = self.client.get(
            reverse("contact-observations-list", kwargs={"contact_pk": self.contact.id}),
            {"is_active": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], active_observation.id)

    def test_old_contact_notes_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("contact-notes-list", kwargs={"contact_pk": self.contact.id})

    def test_old_contact_notes_path_is_removed(self):
        response = self.client.get(f"/api/contacts/{self.contact.id}/notes/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
