from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import UserFactory
from lookups.models import InteractionMode


class InteractionModeModelTests(TestCase):
    def test_str_returns_name(self):
        interaction_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )

        self.assertEqual(str(interaction_mode), "In person")

    def test_db_table_is_interaction_modes(self):
        self.assertEqual(InteractionMode._meta.db_table, "interaction_modes")

    def test_for_user_returns_system_defaults_and_user_rows(self):
        user = UserFactory()
        other_user = UserFactory()
        system_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )
        user_mode = InteractionMode.objects.create(
            user=user,
            name="Book club",
        )
        other_mode = InteractionMode.objects.create(
            user=other_user,
            name="Private",
        )

        modes = InteractionMode.objects.for_user(user)
        mode_ids = {mode.id for mode in modes}

        self.assertIn(system_mode.id, mode_ids)
        self.assertIn(user_mode.id, mode_ids)
        self.assertNotIn(other_mode.id, mode_ids)


class InteractionModeViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_visible_interaction_modes(self):
        system_mode = InteractionMode.objects.create(
            name="In person",
            is_system_default=True,
        )
        user_mode = InteractionMode.objects.create(
            user=self.user,
            name="Book club",
        )
        other_mode = InteractionMode.objects.create(
            user=self.other_user,
            name="Private",
        )

        response = self.client.get(reverse("interaction-mode-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mode_ids = {mode["id"] for mode in response.data}
        self.assertIn(system_mode.id, mode_ids)
        self.assertIn(user_mode.id, mode_ids)
        self.assertNotIn(other_mode.id, mode_ids)

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse("interaction-mode-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_interaction_mode_is_not_allowed_at_v1(self):
        response = self.client.post(
            reverse("interaction-mode-list"),
            {"name": "Walk"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
