from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.models import ContactLooseNote
from lookups.models import ObservationMarker

from .factories import ContactFactory, UserFactory


class ContactLooseNoteObservationMarkerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.contact = ContactFactory(user=self.user)
        self.marker = ObservationMarker.objects.create(
            user=self.user,
            name="Important",
            color_hex="#E53E3E",
            icon_reference="FiAlertCircle",
        )
        self.client.force_authenticate(user=self.user)

    def test_contact_loose_note_accepts_observation_marker(self):
        note = ContactLooseNote.objects.create(
            contact=self.contact,
            marker=self.marker,
            body="Seemed tired after lunch.",
        )

        self.assertEqual(note.marker, self.marker)

    def test_contact_loose_note_endpoint_accepts_observation_marker(self):
        response = self.client.post(
            reverse("contact-notes-list", kwargs={"contact_pk": self.contact.id}),
            {
                "marker": self.marker.id,
                "body": "Seemed tired after lunch.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        note = ContactLooseNote.objects.get(id=response.data["id"])
        self.assertEqual(note.marker, self.marker)
        self.assertEqual(note.contact, self.contact)
