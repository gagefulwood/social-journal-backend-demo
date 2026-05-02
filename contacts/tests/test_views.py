from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.models import Contact

from .factories import ContactFactory, UserFactory


class ContactViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_paginated_contacts_scoped_to_user(self):
        owned_contact = ContactFactory(user=self.user, first_name="Ada")
        ContactFactory(user=self.other_user, first_name="Grace")

        response = self.client.get(reverse("contact-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], owned_contact.id)

    def test_retrieve_returns_404_for_other_users_contact(self):
        other_contact = ContactFactory(user=self.other_user)

        response = self.client.get(reverse("contact-detail", args=[other_contact.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_sets_user_from_request_user(self):
        response = self.client.post(
            reverse("contact-list"),
            {"first_name": "Ada", "last_name": "Lovelace"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.get(id=response.data["id"])
        self.assertEqual(contact.user, self.user)

    def test_create_ignores_user_from_request_body(self):
        response = self.client.post(
            reverse("contact-list"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "user": self.other_user.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.get(id=response.data["id"])
        self.assertEqual(contact.user, self.user)

    def test_partial_update_allows_owner(self):
        contact = ContactFactory(user=self.user, first_name="Ada")

        response = self.client.patch(
            reverse("contact-detail", args=[contact.id]),
            {"first_name": "Augusta"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contact.refresh_from_db()
        self.assertEqual(contact.first_name, "Augusta")

    def test_partial_update_blocks_other_users_contact(self):
        other_contact = ContactFactory(user=self.other_user, first_name="Grace")

        response = self.client.patch(
            reverse("contact-detail", args=[other_contact.id]),
            {"first_name": "Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        other_contact.refresh_from_db()
        self.assertEqual(other_contact.first_name, "Grace")

    def test_delete_hard_deletes_contact(self):
        contact = ContactFactory(user=self.user)

        response = self.client.delete(reverse("contact-detail", args=[contact.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Contact._base_manager.filter(id=contact.id).exists())
