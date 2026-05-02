from django.test import TestCase

from contacts.models import Contact

from .factories import ContactFactory, UserFactory


class ContactManagerTests(TestCase):
    def test_for_user_returns_contacts_owned_by_user(self):
        user = UserFactory()
        owned_contact = ContactFactory(user=user)
        ContactFactory()

        contacts = Contact.objects.for_user(user)

        self.assertEqual(list(contacts), [owned_contact])

    def test_for_user_excludes_inactive_contacts(self):
        user = UserFactory()
        active_contact = ContactFactory(user=user, is_active=True)
        ContactFactory(user=user, is_active=False)

        contacts = Contact.objects.for_user(user)

        self.assertEqual(list(contacts), [active_contact])

    def test_for_user_returns_empty_queryset_for_user_without_contacts(self):
        user = UserFactory()
        ContactFactory()

        contacts = Contact.objects.for_user(user)

        self.assertEqual(list(contacts), [])
