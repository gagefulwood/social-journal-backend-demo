import lookups.models as lookup_models
from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.tests.factories import UserFactory


class ClosenessScoreRemovedTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_closeness_score_model_is_removed_from_active_models(self):
        self.assertFalse(hasattr(lookup_models, "ClosenessScore"))

    def test_closeness_score_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("closeness-score-list")

    def test_closeness_score_path_is_removed(self):
        response = self.client.get("/api/lookups/closeness-scores/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
