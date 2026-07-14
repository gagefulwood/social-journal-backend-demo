from importlib import import_module

from django.apps import apps
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
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

    def test_label_is_optional(self):
        fact = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="A legacy value without a concise label.",
        )

        self.assertIsNone(fact.label)

    def test_pin_and_unpin_are_idempotent(self):
        fact = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Allergic to shellfish.",
        )

        self.assertIsNone(fact.pinned_at)
        self.assertFalse(fact.is_pinned)

        fact.pin()
        first_pinned_at = fact.pinned_at
        self.assertTrue(timezone.is_aware(first_pinned_at))
        self.assertTrue(fact.is_pinned)

        fact.pin()
        fact.refresh_from_db()
        self.assertEqual(fact.pinned_at, first_pinned_at)

        fact.unpin()
        fact.unpin()
        fact.refresh_from_db()
        self.assertIsNone(fact.pinned_at)
        self.assertFalse(fact.is_pinned)

    def test_label_backfill_splits_only_unambiguous_legacy_values(self):
        split_fact = Fact.objects.create(
            contact=self.contact,
            detail_value="Coffee: Oat milk",
        )
        ambiguous_fact = Fact.objects.create(
            contact=self.contact,
            detail_value="Call at 5:30",
        )

        migration = import_module("contacts.migrations.0014_fact_label")
        migration.split_legacy_fact_labels(apps, None)

        split_fact.refresh_from_db()
        ambiguous_fact.refresh_from_db()
        self.assertEqual(split_fact.label, "Coffee")
        self.assertEqual(split_fact.detail_value, "Oat milk")
        self.assertIsNone(ambiguous_fact.label)
        self.assertEqual(ambiguous_fact.detail_value, "Call at 5:30")

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
        self.other_users_category = FactCategory.objects.create(
            user=self.other_user,
            name="Private",
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
                "label": "Allergy",
                "detail_value": "Allergic to shellfish.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact = Fact.objects.get(id=response.data["id"])
        self.assertEqual(fact.category, self.category)
        self.assertEqual(fact.contact, self.contact)
        self.assertEqual(fact.label, "Allergy")

    def test_list_includes_value_alias_and_category_summary(self):
        parent = FactCategory.objects.create(
            user=self.user,
            name="Preferences",
        )
        category = FactCategory.objects.create(
            user=self.user,
            parent=parent,
            name="Coffee",
            icon_reference="FiCoffee",
        )
        Fact.objects.create(
            contact=self.contact,
            category=category,
            label="Coffee",
            detail_value="Oat milk",
        )

        response = self.client.get(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        fact = response.data["results"][0]
        self.assertEqual(fact["label"], "Coffee")
        self.assertEqual(fact["detail_value"], "Oat milk")
        self.assertEqual(fact["value"], "Oat milk")
        self.assertFalse(fact["is_conversation_cue"])
        self.assertEqual(fact["category_summary"], {
            "id": category.id,
            "name": "Coffee",
            "icon_reference": "FiCoffee",
            "parent": {"id": parent.id, "name": "Preferences"},
        })

    def test_value_is_read_only_and_detail_value_remains_required(self):
        response = self.client.post(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id}),
            {"category": self.category.id, "value": "Oat milk"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail_value", response.data)

    def test_patch_fact_allows_a_label(self):
        fact = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Oat milk",
        )

        response = self.client.patch(
            reverse("contact-facts-detail", kwargs={
                "contact_pk": self.contact.id,
                "pk": fact.id,
            }),
            {"label": "Coffee"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["label"], "Coffee")
        fact.refresh_from_db()
        self.assertEqual(fact.label, "Coffee")

    def test_fact_conversation_cue_is_owner_writable_and_filterable(self):
        cue_response = self.client.post(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id}),
            {
                "category": self.category.id,
                "detail_value": "Ask about the spring 10K.",
                "is_conversation_cue": True,
            },
            format="json",
        )
        Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Durable but not a cue.",
        )

        self.assertEqual(cue_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(cue_response.data["is_conversation_cue"])

        filtered_response = self.client.get(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id}),
            {"is_conversation_cue": "true"},
        )
        patch_response = self.client.patch(
            reverse("contact-facts-detail", kwargs={
                "contact_pk": self.contact.id,
                "pk": cue_response.data["id"],
            }),
            {"is_conversation_cue": False},
            format="json",
        )

        self.assertEqual(filtered_response.data["count"], 1)
        self.assertEqual(filtered_response.data["results"][0]["id"], cue_response.data["id"])
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertFalse(patch_response.data["is_conversation_cue"])

    def test_pin_and_unpin_actions_are_idempotent_and_server_controlled(self):
        fact = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Allergic to shellfish.",
        )
        kwargs = {"contact_pk": self.contact.id, "pk": fact.id}

        pin_response = self.client.post(reverse("contact-facts-pin", kwargs=kwargs))
        first_pinned_at = pin_response.data["pinned_at"]
        repeat_response = self.client.post(reverse("contact-facts-pin", kwargs=kwargs))
        patch_response = self.client.patch(
            reverse("contact-facts-detail", kwargs=kwargs),
            {"pinned_at": None, "is_pinned": False},
            format="json",
        )

        self.assertEqual(pin_response.status_code, status.HTTP_200_OK)
        self.assertTrue(pin_response.data["is_pinned"])
        self.assertIsNotNone(first_pinned_at)
        self.assertEqual(repeat_response.data["pinned_at"], first_pinned_at)
        self.assertTrue(patch_response.data["is_pinned"])
        self.assertEqual(patch_response.data["pinned_at"], first_pinned_at)

        unpin_response = self.client.post(reverse("contact-facts-unpin", kwargs=kwargs))
        repeat_unpin_response = self.client.post(
            reverse("contact-facts-unpin", kwargs=kwargs)
        )
        self.assertEqual(unpin_response.status_code, status.HTTP_200_OK)
        self.assertFalse(unpin_response.data["is_pinned"])
        self.assertIsNone(unpin_response.data["pinned_at"])
        self.assertEqual(repeat_unpin_response.data, unpin_response.data)

    def test_pin_filters_and_explicit_ordering_preserve_default_order(self):
        now = timezone.now()
        oldest_pin = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Oldest pin.",
        )
        unpinned = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Unpinned.",
        )
        newest_pin = Fact.objects.create(
            contact=self.contact,
            category=self.category,
            detail_value="Newest pin.",
        )
        Fact.objects.filter(pk=oldest_pin.pk).update(
            pinned_at=now - timezone.timedelta(days=1)
        )
        Fact.objects.filter(pk=newest_pin.pk).update(pinned_at=now)
        url = reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id})

        default_response = self.client.get(url)
        pinned_response = self.client.get(url, {"pinned": "true"})
        unpinned_response = self.client.get(url, {"pinned": "false"})
        newest_first_response = self.client.get(url, {"ordering": "-pinned_at"})
        oldest_first_response = self.client.get(url, {"ordering": "pinned_at"})

        self.assertEqual(
            [item["id"] for item in default_response.data["results"]],
            [oldest_pin.id, unpinned.id, newest_pin.id],
        )
        self.assertEqual(
            [item["id"] for item in pinned_response.data["results"]],
            [oldest_pin.id, newest_pin.id],
        )
        self.assertTrue(all(
            item["is_pinned"] and item["pinned_at"]
            for item in pinned_response.data["results"]
        ))
        self.assertEqual(
            [item["id"] for item in unpinned_response.data["results"]],
            [unpinned.id],
        )
        self.assertFalse(unpinned_response.data["results"][0]["is_pinned"])
        self.assertIsNone(unpinned_response.data["results"][0]["pinned_at"])
        self.assertEqual(
            [item["id"] for item in newest_first_response.data["results"]],
            [newest_pin.id, oldest_pin.id, unpinned.id],
        )
        self.assertEqual(
            [item["id"] for item in oldest_first_response.data["results"]],
            [oldest_pin.id, newest_pin.id, unpinned.id],
        )

    def test_invalid_pin_filter_is_ignored_and_invalid_ordering_is_rejected(self):
        Fact.objects.create(contact=self.contact, detail_value="A fact.")
        url = reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id})

        invalid_boolean_response = self.client.get(url, {"pinned": "sometimes"})
        invalid_ordering_response = self.client.get(url, {"ordering": "id"})

        self.assertEqual(invalid_boolean_response.status_code, status.HTTP_200_OK)
        self.assertEqual(invalid_boolean_response.data["count"], 1)
        self.assertEqual(
            invalid_ordering_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_filter_by_category_and_search(self):
        coffee = FactCategory.objects.create(user=self.user, name="Preferences")
        training = FactCategory.objects.create(user=self.user, name="Training")
        matching_fact = Fact.objects.create(
            contact=self.contact,
            category=coffee,
            label="Coffee",
            detail_value="Oat milk",
        )
        Fact.objects.create(
            contact=self.contact,
            category=training,
            detail_value="Spring 10K",
        )

        category_response = self.client.get(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id}),
            {"category": coffee.id},
        )
        search_response = self.client.get(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id}),
            {"search": "coffee"},
        )

        self.assertEqual(category_response.data["count"], 1)
        self.assertEqual(category_response.data["results"][0]["id"], matching_fact.id)
        self.assertEqual(search_response.data["count"], 1)
        self.assertEqual(search_response.data["results"][0]["id"], matching_fact.id)

    def test_list_uses_loaded_category_relations(self):
        parent = FactCategory.objects.create(user=self.user, name="Preferences")
        category = FactCategory.objects.create(
            user=self.user,
            parent=parent,
            name="Coffee",
        )
        Fact.objects.create(
            contact=self.contact,
            category=category,
            detail_value="Oat milk",
        )

        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id})
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_rejects_another_users_fact_category(self):
        response = self.client.post(
            reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id}),
            {
                "category": self.other_users_category.id,
                "detail_value": "Private category injection.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)

    def test_other_users_contact_is_inaccessible(self):
        response = self.client.get(
            reverse("contact-facts-list", kwargs={"contact_pk": self.other_contact.id})
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_users_fact_cannot_be_pinned(self):
        fact = Fact.objects.create(
            contact=self.other_contact,
            detail_value="Other user's fact.",
        )

        response = self.client.post(reverse("contact-facts-pin", kwargs={
            "contact_pk": self.other_contact.id,
            "pk": fact.id,
        }))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        fact.refresh_from_db()
        self.assertFalse(fact.is_pinned)

    def test_deleting_a_pinned_fact_removes_it(self):
        fact = Fact.objects.create(contact=self.contact, detail_value="Temporary.")
        fact.pin()

        response = self.client.delete(reverse("contact-facts-detail", kwargs={
            "contact_pk": self.contact.id,
            "pk": fact.id,
        }))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Fact.objects.filter(pk=fact.id).exists())

    def test_inactive_contact_is_inaccessible_for_list_and_create(self):
        self.contact.is_active = False
        self.contact.save(update_fields=["is_active"])
        url = reverse("contact-facts-list", kwargs={"contact_pk": self.contact.id})

        list_response = self.client.get(url)
        create_response = self.client.post(
            url,
            {"category": self.category.id, "detail_value": "Should not save."},
            format="json",
        )

        self.assertEqual(list_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(create_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_old_contact_details_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("contact-details-list", kwargs={"contact_pk": self.contact.id})

    def test_old_contact_details_path_is_removed(self):
        response = self.client.get(f"/api/contacts/{self.contact.id}/details/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
