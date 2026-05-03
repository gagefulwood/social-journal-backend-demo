from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from contacts.tests.factories import UserFactory
from lookups.models import MediaType


class MediaTypeViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_system_default_media_types(self):
        image = MediaType.objects.create(name="IMAGE", is_system_default=True)
        MediaType.objects.create(name="INTERNAL", is_system_default=False)

        response = self.client.get(reverse("media-type-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        media_type_ids = {media_type["id"] for media_type in response.data}
        self.assertIn(image.id, media_type_ids)

    def test_list_excludes_non_system_media_types(self):
        MediaType.objects.create(name="IMAGE", is_system_default=True)
        internal = MediaType.objects.create(name="INTERNAL", is_system_default=False)

        response = self.client.get(reverse("media-type-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        media_type_ids = {media_type["id"] for media_type in response.data}
        self.assertNotIn(internal.id, media_type_ids)
