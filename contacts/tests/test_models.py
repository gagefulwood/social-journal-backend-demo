from django.test import TestCase

from contacts.models import Contact

from .factories import ContactFactory, UserFactory


class ContactModelTests(TestCase):
    def test_contact_has_expected_stable_fields(self):
        field_names = {field.name for field in Contact._meta.fields}

        expected_fields = {
            "id",
            "user",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "phone_number",
            "is_active",
            "address",
            "birthday",
            "first_met_date",
            "occupation",
            "custom_occupation",
            "company",
            "education_level",
            "custom_education_level",
            "school",
            "closeness_score",
        }

        self.assertTrue(expected_fields.issubset(field_names))

    def test_str_returns_trimmed_full_name(self):
        contact = ContactFactory(first_name="Ada", last_name="Lovelace")

        self.assertEqual(str(contact), "Ada Lovelace")

    def test_str_omits_blank_last_name_spacing(self):
        contact = ContactFactory(first_name="Ada", last_name="")

        self.assertEqual(str(contact), "Ada")

    def test_is_active_defaults_to_true(self):
        user = UserFactory()
        contact = Contact.objects.create(user=user, first_name="Ada")

        self.assertTrue(contact.is_active)

    def test_db_table_is_contacts(self):
        self.assertEqual(Contact._meta.db_table, "contacts")
