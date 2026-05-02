from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.models import ContactPersonalDetail
from lookups.models import FactCategory

from .factories import ContactFactory, UserFactory


class ContactPersonalDetailFactCategoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.contact = ContactFactory(user=self.user)
        self.category = FactCategory.objects.create(
            user=self.user,
            name="Health",
            icon_reference="FiHeart",
        )
        self.client.force_authenticate(user=self.user)

    def test_contact_personal_detail_accepts_fact_category(self):
        detail = ContactPersonalDetail.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Allergic to shellfish.",
        )

        self.assertEqual(detail.category, self.category)

    def test_contact_personal_detail_endpoint_accepts_fact_category(self):
        response = self.client.post(
            reverse("contact-details-list", kwargs={"contact_pk": self.contact.id}),
            {
                "category": self.category.id,
                "detail_value": "Allergic to shellfish.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        detail = ContactPersonalDetail.objects.get(id=response.data["id"])
        self.assertEqual(detail.category, self.category)
        self.assertEqual(detail.contact, self.contact)
