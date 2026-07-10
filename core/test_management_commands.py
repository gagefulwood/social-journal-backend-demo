from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from contacts.models import Contact
from events.models import Event
from journals.models import Exercise, Log, Reflection
from users.models import Users


class PopulateAccountCommandTests(TestCase):
    def setUp(self):
        self.user = Users.objects.create_user(
            email="gage@example.com",
            username="gage",
            first_name="Gage",
            last_name="Fulwood",
            password="test-password",
        )

    def test_populates_only_the_selected_existing_account(self):
        other_user = Users.objects.create_user(
            email="other@example.com",
            username="other",
            first_name="Other",
            last_name="User",
            password="test-password",
        )

        call_command("populate_account", "Gage Fulwood", stdout=StringIO())

        self.assertEqual(Contact.objects.filter(user=self.user).count(), 5)
        self.assertEqual(Event.objects.filter(user=self.user).count(), 8)
        self.assertEqual(Log.objects.filter(user=self.user).count(), 4)
        self.assertEqual(Reflection.objects.filter(user=self.user).count(), 2)
        self.assertEqual(Exercise.objects.filter(user=self.user).count(), 2)
        self.assertFalse(Contact.objects.filter(user=other_user).exists())

    def test_is_idempotent(self):
        call_command("populate_account", self.user.username, stdout=StringIO())
        first_counts = (
            Contact.objects.filter(user=self.user).count(),
            Event.objects.filter(user=self.user).count(),
            Log.objects.filter(user=self.user).count(),
            Reflection.objects.filter(user=self.user).count(),
            Exercise.objects.filter(user=self.user).count(),
        )

        output = StringIO()
        call_command("populate_account", self.user.email, stdout=output)

        self.assertEqual(
            first_counts,
            (
                Contact.objects.filter(user=self.user).count(),
                Event.objects.filter(user=self.user).count(),
                Log.objects.filter(user=self.user).count(),
                Reflection.objects.filter(user=self.user).count(),
                Exercise.objects.filter(user=self.user).count(),
            ),
        )
        self.assertIn("already has the demo dataset", output.getvalue())

    def test_dry_run_rolls_back_everything(self):
        output = StringIO()

        call_command(
            "populate_account",
            self.user.username,
            dry_run=True,
            stdout=output,
        )

        self.assertFalse(Contact.objects.filter(user=self.user).exists())
        self.assertFalse(Event.objects.filter(user=self.user).exists())
        self.assertIn("Would create", output.getvalue())

    def test_rejects_an_ambiguous_full_name(self):
        Users.objects.create_user(
            email="another-gage@example.com",
            username="another-gage",
            first_name="Gage",
            last_name="Fulwood",
            password="test-password",
        )

        with self.assertRaisesMessage(CommandError, "More than one user matched"):
            call_command("populate_account", "Gage Fulwood", stdout=StringIO())
