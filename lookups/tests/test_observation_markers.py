from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.tests.factories import UserFactory
from lookups.models import ObservationMarker


class ObservationMarkerModelTests(TestCase):
    def test_str_returns_name(self):
        marker = ObservationMarker.objects.create(
            name="Important",
            color_hex="#E53E3E",
            icon_reference="FiAlertCircle",
            is_system_default=True,
        )

        self.assertEqual(str(marker), "Important")

    def test_db_table_is_observation_markers(self):
        self.assertEqual(ObservationMarker._meta.db_table, "observation_markers")

    def test_for_user_returns_system_defaults_and_user_rows(self):
        user = UserFactory()
        other_user = UserFactory()
        system_marker = ObservationMarker.objects.create(
            name="General",
            color_hex="#718096",
            is_system_default=True,
        )
        user_marker = ObservationMarker.objects.create(
            user=user,
            name="Personal",
            color_hex="#2B6CB0",
        )
        ObservationMarker.objects.create(
            user=other_user,
            name="Other",
            color_hex="#805AD5",
        )

        markers = ObservationMarker.objects.for_user(user)
        marker_ids = {marker.id for marker in markers}

        self.assertIn(system_marker.id, marker_ids)
        self.assertIn(user_marker.id, marker_ids)
        self.assertNotIn(
            ObservationMarker.objects.get(user=other_user, name="Other").id,
            marker_ids,
        )
        self.assertTrue(
            all(marker.is_system_default or marker.user == user for marker in markers)
        )


class ObservationMarkerViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_visible_observation_markers(self):
        system_marker = ObservationMarker.objects.create(
            name="General",
            color_hex="#718096",
            icon_reference="FiFileText",
            is_system_default=True,
        )
        user_marker = ObservationMarker.objects.create(
            user=self.user,
            name="Personal",
            color_hex="#2B6CB0",
            icon_reference="FiUser",
        )
        ObservationMarker.objects.create(
            user=self.other_user,
            name="Other",
            color_hex="#805AD5",
            icon_reference="FiUsers",
        )

        response = self.client.get(reverse("observation-marker-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        marker_ids = {marker["id"] for marker in response.data}
        other_marker = ObservationMarker.objects.get(user=self.other_user, name="Other")
        self.assertIn(system_marker.id, marker_ids)
        self.assertIn(user_marker.id, marker_ids)
        self.assertNotIn(other_marker.id, marker_ids)
        self.assertTrue(
            all(
                ObservationMarker.objects.get(id=marker_id).is_system_default
                or ObservationMarker.objects.get(id=marker_id).user == self.user
                for marker_id in marker_ids
            )
        )

    def test_note_markers_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("note-marker-list")

    def test_note_markers_path_is_removed(self):
        response = self.client.get("/api/lookups/note-markers/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
