from datetime import date
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.test import TestCase

from contacts.models import ContactAddress, ContactEducation, ContactEmployment

from .factories import ContactFactory, UserFactory


class ContactProfileApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_legacy_contact_has_empty_additive_profile_shape(self):
        contact = ContactFactory(
            user=self.user,
            email='legacy@example.com',
            phone_number='+1 555 0101',
            address='Old freeform address',
        )

        response = self.client.get(reverse('contact-detail', args=[contact.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'legacy@example.com')
        self.assertEqual(response.data['address'], 'Old freeform address')
        self.assertEqual(response.data['contact_methods'], [])
        self.assertEqual(response.data['addresses'], [])
        self.assertIsNone(response.data['age'])

    @patch('contacts.serializers.date')
    def test_age_accounts_for_birthday_before_on_and_after_today(self, mocked_date):
        mocked_date.today.return_value = date(2026, 7, 12)
        birthdays = {
            'before': ('1996-07-11', 30),
            'on': ('1996-07-12', 30),
            'after': ('1996-07-13', 29),
        }
        for name, (birthday, expected_age) in birthdays.items():
            with self.subTest(name=name):
                contact = ContactFactory(user=self.user, birthday=birthday)
                response = self.client.get(
                    reverse('contact-detail', args=[contact.id])
                )
                self.assertEqual(response.data['birth_date'], birthday)
                self.assertEqual(response.data['age'], expected_age)

    def test_create_structured_profile_and_preserves_legacy_address(self):
        response = self.client.post(
            reverse('contact-list'),
            {
                'first_name': 'Alex',
                'last_name': 'Rivera',
                'address': 'Legacy address kept verbatim',
                'birth_date': '1999-05-19',
                'first_met_on': '2024-07-09',
                'timezone': 'America/Chicago',
                'contact_methods': [
                    {'kind': 'email', 'label': 'Personal', 'value': 'alex@example.com', 'is_primary': True},
                    {'kind': 'email', 'label': 'Work', 'value': 'alex@work.example', 'is_primary': False},
                    {'kind': 'phone', 'label': 'Mobile', 'value': '+1 555-0101', 'is_primary': True},
                ],
                'addresses': [
                    {'label': 'Home', 'line_1': '210 College View Dr', 'city': 'Starkville', 'region': 'MS', 'postal_code': '39759', 'country_code': 'us', 'is_primary': True},
                ],
                'employment': [
                    {'title': 'Product designer', 'organization': 'Northstar Studio', 'start_date': '2024-01-01', 'is_current': True},
                ],
                'education': [
                    {'credential': 'B.S.', 'field_of_study': 'Computer Science', 'institution': 'Mississippi State University', 'end_date': '2021-05-01'},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['birthday'], '1999-05-19')
        self.assertEqual(response.data['first_met_date'], '2024-07-09')
        self.assertEqual(response.data['address'], 'Legacy address kept verbatim')
        self.assertEqual(response.data['addresses'][0]['country_code'], 'US')
        self.assertEqual(len(response.data['contact_methods']), 3)

    def test_nested_patch_does_not_wipe_omitted_collections(self):
        contact = ContactFactory(user=self.user)
        ContactAddress.objects.create(contact=contact, line_1='One Main St')
        ContactEmployment.objects.create(contact=contact, title='Designer')
        ContactEducation.objects.create(contact=contact, institution='State U')

        response = self.client.patch(
            reverse('contact-detail', args=[contact.id]),
            {'preferred_name': 'Lex'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(contact.addresses.count(), 1)
        self.assertEqual(contact.employment.count(), 1)
        self.assertEqual(contact.education.count(), 1)

    def test_rejects_invalid_nested_and_read_only_values(self):
        invalid_payloads = [
            {'age': 30},
            {'timezone': 'Central-ish'},
            {'contact_methods': [{'kind': 'email', 'value': 'not-email', 'is_primary': True}]},
            {'contact_methods': [{'kind': 'phone', 'value': '123', 'is_primary': True}]},
            {'contact_methods': [
                {'kind': 'email', 'value': 'one@example.com', 'is_primary': True},
                {'kind': 'email', 'value': 'two@example.com', 'is_primary': True},
            ]},
            {'addresses': [
                {'line_1': 'One', 'is_primary': True},
                {'line_1': 'Two', 'is_primary': True},
            ]},
            {'addresses': [{'line_1': 'One', 'country_code': 'USA'}]},
            {'employment': [{'title': 'Designer', 'start_date': '2025-01-02', 'end_date': '2025-01-01'}]},
            {'education': [{'institution': 'State U', 'end_date': '2025-01-01', 'is_current': True}]},
        ]
        contact = ContactFactory(user=self.user)
        url = reverse('contact-detail', args=[contact.id])

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.patch(url, payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nested_update_create_and_delete_are_transactional(self):
        contact = ContactFactory(user=self.user)
        job = ContactEmployment.objects.create(
            contact=contact,
            title='Designer',
            organization='Old Studio',
        )

        response = self.client.patch(
            reverse('contact-detail', args=[contact.id]),
            {
                'employment': [
                    {'id': job.id, 'title': 'Senior designer', 'organization': 'Northstar'},
                    {'title': 'Advisor', 'organization': 'Community Lab'},
                ],
                'education': [{'institution': 'Mississippi State University'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(contact.employment.count(), 2)
        job.refresh_from_db()
        self.assertEqual(job.title, 'Senior designer')
        self.assertEqual(contact.education.count(), 1)
        self.assertEqual(response.data['employment'][0]['title'], 'Senior designer')
        self.assertEqual(response.data['education'][0]['institution'], 'Mississippi State University')
