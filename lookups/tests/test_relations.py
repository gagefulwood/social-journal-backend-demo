from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import UserFactory
from lookups.models import Relation


class RelationModelTests(TestCase):
    def test_str_returns_name(self):
        relation = Relation.objects.create(name="Friend", is_system_default=True)

        self.assertEqual(str(relation), "Friend")

    def test_db_table_is_relations(self):
        self.assertEqual(Relation._meta.db_table, "relations")

    def test_for_user_returns_system_defaults_and_user_rows(self):
        user = UserFactory()
        other_user = UserFactory()
        system_relation = Relation.objects.create(
            name="Friend",
            is_system_default=True,
        )
        user_relation = Relation.objects.create(
            user=user,
            name="Book Club",
        )
        other_relation = Relation.objects.create(
            user=other_user,
            name="Private",
        )

        relations = Relation.objects.for_user(user)
        relation_ids = {relation.id for relation in relations}

        self.assertIn(system_relation.id, relation_ids)
        self.assertIn(user_relation.id, relation_ids)
        self.assertNotIn(other_relation.id, relation_ids)
        self.assertTrue(
            all(relation.is_system_default or relation.user == user for relation in relations)
        )


class RelationViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_visible_relations(self):
        system_relation = Relation.objects.create(
            name="Friend",
            is_system_default=True,
        )
        user_relation = Relation.objects.create(
            user=self.user,
            name="Book Club",
        )
        other_relation = Relation.objects.create(
            user=self.other_user,
            name="Private",
        )

        response = self.client.get(reverse("relation-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        relation_ids = {relation["id"] for relation in response.data}
        self.assertIn(system_relation.id, relation_ids)
        self.assertIn(user_relation.id, relation_ids)
        self.assertNotIn(other_relation.id, relation_ids)

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse("relation-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_relation_is_not_allowed_at_mvp(self):
        response = self.client.post(
            reverse("relation-list"),
            {"name": "Teammate"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
