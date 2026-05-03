from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.models import Contact
from contacts.filters import ContactFilter
from lookups.models import Occupation, Relation
from media.tests.factories import MediaAssetFactory

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
        self.assertIsNone(response.data["results"][0]["relation_name"])
        self.assertIsNone(response.data["results"][0]["occupation_name"])

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
                "connection_strength": 100,
                "relationship_trend": "growing",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.get(id=response.data["id"])
        self.assertEqual(contact.user, self.user)
        self.assertEqual(contact.connection_strength, 0)
        self.assertEqual(contact.relationship_trend, "dormant")

    def test_list_includes_relationship_statistics(self):
        contact = ContactFactory(
            user=self.user,
            interaction_frequency_score=30,
            relationship_trend="growing",
            connection_strength=60,
        )

        response = self.client.get(reverse("contact-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data["results"][0]
        self.assertEqual(result["id"], contact.id)
        self.assertEqual(result["interaction_frequency_score"], 30)
        self.assertEqual(result["relationship_trend"], "growing")
        self.assertEqual(result["connection_strength"], 60)
        self.assertIn("profile_picture", result)
        self.assertNotIn("closeness_score", result)

    def test_detail_excludes_closeness_score(self):
        contact = ContactFactory(user=self.user)

        response = self.client.get(reverse("contact-detail", args=[contact.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("closeness_score", response.data)

    def test_filter_no_longer_exposes_closeness_score(self):
        self.assertNotIn("closeness_score", ContactFilter.get_filters())

    def test_create_sets_relation(self):
        relation = Relation.objects.create(name="Friend", is_system_default=True)

        response = self.client.post(
            reverse("contact-list"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "relation": relation.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.get(id=response.data["id"])
        self.assertEqual(contact.relation, relation)
        self.assertEqual(response.data["relation"], relation.id)
        self.assertEqual(response.data["relation_name"], "Friend")

    def test_partial_update_sets_relation(self):
        contact = ContactFactory(user=self.user)
        relation = Relation.objects.create(name="Coworker", is_system_default=True)

        response = self.client.patch(
            reverse("contact-detail", args=[contact.id]),
            {"relation": relation.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contact.refresh_from_db()
        self.assertEqual(contact.relation, relation)
        self.assertEqual(response.data["relation"], relation.id)
        self.assertEqual(response.data["relation_name"], "Coworker")

    def test_partial_update_clears_relation(self):
        relation = Relation.objects.create(name="Friend", is_system_default=True)
        contact = ContactFactory(user=self.user, relation=relation)

        response = self.client.patch(
            reverse("contact-detail", args=[contact.id]),
            {"relation": None},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contact.refresh_from_db()
        self.assertIsNone(contact.relation)
        self.assertIsNone(response.data["relation"])

    def test_partial_update_rejects_other_users_relation(self):
        contact = ContactFactory(user=self.user)
        private_relation = Relation.objects.create(
            user=self.other_user,
            name="Private",
        )

        response = self.client.patch(
            reverse("contact-detail", args=[contact.id]),
            {"relation": private_relation.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        contact.refresh_from_db()
        self.assertIsNone(contact.relation)

    def test_detail_includes_relation_and_occupation_display_names(self):
        relation = Relation.objects.create(name="Neighbor", is_system_default=True)
        occupation = Occupation.objects.create(name="Designer", is_system_default=True)
        contact = ContactFactory(
            user=self.user,
            relation=relation,
            occupation=occupation,
        )

        response = self.client.get(reverse("contact-detail", args=[contact.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["relation"], relation.id)
        self.assertEqual(response.data["relation_name"], "Neighbor")
        self.assertEqual(response.data["occupation"], occupation.id)
        self.assertEqual(response.data["occupation_name"], "Designer")

    def test_list_includes_relation_and_occupation_display_names(self):
        relation = Relation.objects.create(name="Classmate", is_system_default=True)
        occupation = Occupation.objects.create(name="Engineer", is_system_default=True)
        contact = ContactFactory(
            user=self.user,
            relation=relation,
            occupation=occupation,
        )

        response = self.client.get(reverse("contact-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data["results"][0]
        self.assertEqual(result["id"], contact.id)
        self.assertEqual(result["relation"], relation.id)
        self.assertEqual(result["relation_name"], "Classmate")
        self.assertEqual(result["occupation"], occupation.id)
        self.assertEqual(result["occupation_name"], "Engineer")

    def test_filter_by_relation(self):
        friend = Relation.objects.create(name="Friend", is_system_default=True)
        coworker = Relation.objects.create(name="Coworker", is_system_default=True)
        included = ContactFactory(user=self.user, relation=friend)
        ContactFactory(user=self.user, relation=coworker)
        ContactFactory(user=self.other_user, relation=friend)

        response = self.client.get(reverse("contact-list"), {"relation": friend.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contact_ids = {contact["id"] for contact in response.data["results"]}
        self.assertEqual(contact_ids, {included.id})

    def test_partial_update_sets_profile_picture_owned_by_user(self):
        contact = ContactFactory(user=self.user)
        asset = MediaAssetFactory(user=self.user, content_type="image/png")

        response = self.client.patch(
            reverse("contact-detail", args=[contact.id]),
            {"profile_picture_id": asset.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contact.refresh_from_db()
        self.assertEqual(contact.profile_picture, asset)
        self.assertEqual(response.data["profile_picture"]["id"], asset.id)

    def test_partial_update_rejects_other_users_profile_picture(self):
        contact = ContactFactory(user=self.user)
        asset = MediaAssetFactory(user=self.other_user, content_type="image/png")

        response = self.client.patch(
            reverse("contact-detail", args=[contact.id]),
            {"profile_picture_id": asset.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        contact.refresh_from_db()
        self.assertIsNone(contact.profile_picture)

    def test_partial_update_rejects_non_image_profile_picture(self):
        contact = ContactFactory(user=self.user)
        asset = MediaAssetFactory(
            user=self.user,
            original_filename="document.pdf",
            content_type="application/pdf",
        )

        response = self.client.patch(
            reverse("contact-detail", args=[contact.id]),
            {"profile_picture_id": asset.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        contact.refresh_from_db()
        self.assertIsNone(contact.profile_picture)

    def test_partial_update_clears_profile_picture(self):
        asset = MediaAssetFactory(user=self.user, content_type="image/png")
        contact = ContactFactory(user=self.user, profile_picture=asset)

        response = self.client.patch(
            reverse("contact-detail", args=[contact.id]),
            {"profile_picture_id": None},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contact.refresh_from_db()
        self.assertIsNone(contact.profile_picture)

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
