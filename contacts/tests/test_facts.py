from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.models import Fact
from lookups.models import FactCategory

from .factories import ContactFactory, UserFactory


class FactModelTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.contact = ContactFactory(user=self.user, first_name="Ada", last_name="Lovelace")
        self.category = FactCategory.objects.create(
            user=self.user,
            name="Health",
            icon_reference="FiHeart",
        )

    def test_str_returns_contact_category_and_detail_value(self):
        fact = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Allergic to shellfish.",
        )

        self.assertEqual(
            str(fact),
            "Ada Lovelace - Health: Allergic to shellfish.",
        )

    def test_db_table_is_facts(self):
        self.assertEqual(Fact._meta.db_table, "facts")

    def test_contact_facts_reverse_accessor_returns_facts(self):
        fact = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Allergic to shellfish.",
        )

        self.assertEqual(list(self.contact.facts.all()), [fact])

    def test_fact_category_facts_reverse_accessor_returns_facts(self):
        fact = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Allergic to shellfish.",
        )

        self.assertEqual(list(self.category.facts.all()), [fact])


class FactViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.contact = ContactFactory(user=self.user)
        self.other_contact = ContactFactory(user=self.other_user)
        self.category = FactCategory.objects.create(
            user=self.user,
            name="Health",
            icon_reference="FiHeart",
        )
        self.client.force_authenticate(user=self.user)

    def test_list_returns_facts_for_contact_owner(self):
        fact = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Allergic to shellfish.",
        )
        Fact.objects.create(
            contact=self.other_contact,
            detail_value="Other user's fact.",
        )

        response = self.client.get(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], fact.id)

    def test_create_fact_sets_contact_from_url(self):
        response = self.client.post(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id}),
            {
                "category": self.category.id,
                "detail_value": "Allergic to shellfish.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact = Fact.objects.get(id=response.data["id"])
        self.assertEqual(fact.category, self.category)
        self.assertEqual(fact.contact, self.contact)

    def test_old_contact_details_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("contact-details-list", kwargs={"contact_pk": self.contact.id})

    def test_old_contact_details_path_is_removed(self):
        response = self.client.get(f"/api/contacts/{self.contact.id}/details/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
