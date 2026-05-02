from django.test import TestCase
from rest_framework.test import APIRequestFactory

from contacts.tests.factories import ContactFactory, UserFactory
from core.permissions import IsOwner


class IsOwnerTests(TestCase):
    def setUp(self):
        self.permission = IsOwner()
        self.factory = APIRequestFactory()

    def test_has_object_permission_returns_true_when_request_user_owns_object(self):
        user = UserFactory()
        contact = ContactFactory(user=user)
        request = self.factory.get("/")
        request.user = user

        result = self.permission.has_object_permission(request, None, contact)

        self.assertTrue(result)

    def test_has_object_permission_returns_false_for_different_owner(self):
        user = UserFactory()
        other_user = UserFactory()
        contact = ContactFactory(user=other_user)
        request = self.factory.get("/")
        request.user = user

        result = self.permission.has_object_permission(request, None, contact)

        self.assertFalse(result)
