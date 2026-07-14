from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from contacts.models import (
    Contact,
    ContactAddress,
    ContactEducation,
    ContactEmployment,
    ContactMethod,
    Fact,
    Observation,
)
from events.models import Event, EventParticipant
from journals.models import Exercise, Log, Reflection
from lookups.models import FactCategory
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
        self.assertEqual(Event.objects.filter(user=self.user).count(), 48)
        self.assertEqual(Log.objects.filter(user=self.user).count(), 4)
        self.assertEqual(Reflection.objects.filter(user=self.user).count(), 2)
        self.assertEqual(Exercise.objects.filter(user=self.user).count(), 2)
        self.assertEqual(
            FactCategory.objects.filter(user=self.user).count(),
            6,
        )
        self.assertTrue(
            Fact.objects.filter(contact__user=self.user, category__isnull=False).exists()
        )
        self.assertTrue(
            Observation.objects.filter(
                contact__user=self.user,
                observation_type__isnull=False,
                occurred_at__isnull=False,
            ).exists()
        )
        self.assertFalse(Contact.objects.filter(user=other_user).exists())

    def test_seeds_ten_historical_events_for_each_of_four_months(self):
        call_command("populate_account", self.user.username, stdout=StringIO())

        historical_events = Event.objects.filter(
            user=self.user,
            title__startswith="Demo history ",
        )
        self.assertEqual(historical_events.count(), 40)

        for month_number in range(1, 5):
            self.assertEqual(
                historical_events.filter(
                    title__startswith=f"Demo history M{month_number}:",
                ).count(),
                10,
            )

        for contact in Contact.objects.filter(user=self.user):
            self.assertEqual(
                EventParticipant.objects.filter(
                    contact=contact,
                    event__in=historical_events,
                ).count(),
                8,
            )

    def test_is_idempotent(self):
        call_command("populate_account", self.user.username, stdout=StringIO())
        first_counts = (
            Contact.objects.filter(user=self.user).count(),
            Event.objects.filter(user=self.user).count(),
            Log.objects.filter(user=self.user).count(),
            Reflection.objects.filter(user=self.user).count(),
            Exercise.objects.filter(user=self.user).count(),
            Fact.objects.filter(contact__user=self.user).count(),
            Observation.objects.filter(contact__user=self.user).count(),
            FactCategory.objects.filter(user=self.user).count(),
            ContactMethod.objects.filter(contact__user=self.user).count(),
            ContactAddress.objects.filter(contact__user=self.user).count(),
            ContactEmployment.objects.filter(contact__user=self.user).count(),
            ContactEducation.objects.filter(contact__user=self.user).count(),
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
                Fact.objects.filter(contact__user=self.user).count(),
                Observation.objects.filter(contact__user=self.user).count(),
                FactCategory.objects.filter(user=self.user).count(),
                ContactMethod.objects.filter(contact__user=self.user).count(),
                ContactAddress.objects.filter(contact__user=self.user).count(),
                ContactEmployment.objects.filter(contact__user=self.user).count(),
                ContactEducation.objects.filter(contact__user=self.user).count(),
            ),
        )
        self.assertIn("already has the demo dataset", output.getvalue())

    def test_seeds_profile_demo_states_without_duplicate_nested_records(self):
        call_command("populate_account", self.user.username, stdout=StringIO())
        call_command("populate_account", self.user.email, stdout=StringIO())

        alex = Contact.objects.get(user=self.user, email="alex.rivera@example.com")
        self.assertEqual(alex.gender_identity, "Man")
        self.assertEqual(alex.pronouns, "He/him")
        self.assertEqual(str(alex.birthday), "1999-05-19")
        self.assertEqual(alex.timezone, "America/Chicago")
        self.assertEqual(str(alex.first_met_date), "2024-07-09")
        self.assertEqual(alex.met_through, "University")
        self.assertEqual(alex.met_location, "Starkville, MS")
        self.assertEqual(alex.contact_methods.count(), 2)
        self.assertEqual(alex.addresses.count(), 1)
        self.assertEqual(alex.employment.count(), 1)
        self.assertEqual(alex.education.count(), 1)
        self.assertEqual(
            alex.contact_methods.filter(kind="email", is_primary=True).count(),
            1,
        )
        self.assertEqual(
            alex.contact_methods.filter(kind="phone", is_primary=True).count(),
            1,
        )
        self.assertEqual(alex.addresses.filter(is_primary=True).count(), 1)

        legacy = Contact.objects.get(
            user=self.user,
            email="jordan.lee.demo@example.com",
        )
        self.assertTrue(legacy.address)
        self.assertFalse(legacy.contact_methods.exists())
        self.assertFalse(legacy.addresses.exists())

        sparse = Contact.objects.get(
            user=self.user,
            email="priya.shah.demo@example.com",
        )
        self.assertEqual(sparse.preferred_name, "Priya")
        self.assertEqual(sparse.contact_methods.count(), 1)
        self.assertFalse(sparse.addresses.exists())
        self.assertFalse(sparse.employment.exists())
        self.assertFalse(sparse.education.exists())

        multiple = Contact.objects.get(
            user=self.user,
            email="marcus.chen.demo@example.com",
        )
        self.assertEqual(multiple.contact_methods.count(), 4)
        self.assertEqual(multiple.addresses.count(), 2)
        self.assertEqual(multiple.employment.count(), 2)
        self.assertEqual(multiple.education.count(), 2)
        self.assertEqual(
            multiple.contact_methods.filter(kind="email", is_primary=True).count(),
            1,
        )
        self.assertEqual(
            multiple.contact_methods.filter(kind="phone", is_primary=True).count(),
            1,
        )
        self.assertEqual(multiple.addresses.filter(is_primary=True).count(), 1)

    def test_updates_the_legacy_alex_seed_identity_without_duplication(self):
        legacy_alex = Contact.objects.create(
            user=self.user,
            first_name="Alex",
            last_name="Rivera",
            email="alex.rivera.demo@example.com",
            phone_number="+1-555-0101",
        )

        call_command("populate_account", self.user.username, stdout=StringIO())

        legacy_alex.refresh_from_db()
        self.assertEqual(legacy_alex.email, "alex.rivera@example.com")
        self.assertEqual(legacy_alex.gender_identity, "Man")
        self.assertEqual(
            Contact.objects.filter(user=self.user, first_name="Alex", last_name="Rivera").count(),
            1,
        )

    def test_seeds_context_categories_types_statuses_and_shared_event_links(self):
        call_command("populate_account", self.user.username, stdout=StringIO())

        facts = Fact.objects.filter(contact__user=self.user).select_related("category")
        observations = Observation.objects.filter(contact__user=self.user).select_related(
            "contact",
            "event",
        )

        self.assertTrue(facts.exists())
        self.assertTrue(all(fact.category_id for fact in facts))
        self.assertTrue(all(fact.label for fact in facts))
        self.assertEqual(facts.get(label="Coffee").detail_value, "Oat milk")
        self.assertEqual(facts.get(label="Training").detail_value, "Spring 10K")
        self.assertEqual(
            set(FactCategory.objects.filter(user=self.user).values_list("name", flat=True)),
            {
                "Preferences",
                "Routines & goals",
                "Work & school",
                "Important dates",
                "Family & relationships",
                "Practical details",
            },
        )
        self.assertEqual(
            set(observations.values_list("observation_type", flat=True)),
            {"notice", "conversation_cue", "appreciation", "change"},
        )
        self.assertEqual(
            set(observations.values_list("status", flat=True)),
            {"current", "revisit_later", "archived"},
        )

        for observation in observations:
            self.assertIsNotNone(observation.occurred_at)
            self.assertIsNotNone(observation.event_id)
            self.assertEqual(observation.event.user_id, self.user.id)
            self.assertTrue(
                EventParticipant.objects.filter(
                    event=observation.event,
                    contact=observation.contact,
                ).exists()
            )
        self.assertFalse(observations.get(status="archived").is_active)
        self.assertTrue(observations.exclude(status="archived").filter(is_active=True).exists())

    def test_seeds_deterministic_pinned_and_unpinned_context(self):
        call_command("populate_account", self.user.username, stdout=StringIO())
        alex = Contact.objects.get(
            user=self.user,
            email="alex.rivera@example.com",
        )

        pinned_facts = list(
            Fact.objects.filter(contact=alex, pinned_at__isnull=False)
            .order_by("-pinned_at")
            .values_list("label", "pinned_at")
        )
        pinned_observations = list(
            Observation.objects.filter(contact=alex, pinned_at__isnull=False)
            .order_by("-pinned_at")
            .values_list("body", "pinned_at")
        )

        self.assertEqual(
            [label for label, _ in pinned_facts],
            ["Coffee", "Training", "Project"],
        )
        self.assertEqual(
            [body for body, _ in pinned_observations],
            [
                "Ask how the new project launch went.",
                "Alex seemed energized about the project.",
                "They made time to check in during a busy week.",
            ],
        )
        self.assertTrue(Fact.objects.filter(contact=alex, pinned_at__isnull=True).exists())
        self.assertTrue(
            Observation.objects.filter(contact=alex, pinned_at__isnull=True).exists()
        )

        first_fact_timestamps = pinned_facts
        first_observation_timestamps = pinned_observations
        call_command("populate_account", self.user.email, stdout=StringIO())

        self.assertEqual(
            list(
                Fact.objects.filter(contact=alex, pinned_at__isnull=False)
                .order_by("-pinned_at")
                .values_list("label", "pinned_at")
            ),
            first_fact_timestamps,
        )
        self.assertEqual(
            list(
                Observation.objects.filter(contact=alex, pinned_at__isnull=False)
                .order_by("-pinned_at")
                .values_list("body", "pinned_at")
            ),
            first_observation_timestamps,
        )

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
        self.assertFalse(FactCategory.objects.filter(user=self.user).exists())
        self.assertFalse(Fact.objects.filter(contact__user=self.user).exists())
        self.assertFalse(Observation.objects.filter(contact__user=self.user).exists())
        self.assertFalse(ContactMethod.objects.filter(contact__user=self.user).exists())
        self.assertFalse(ContactAddress.objects.filter(contact__user=self.user).exists())
        self.assertFalse(ContactEmployment.objects.filter(contact__user=self.user).exists())
        self.assertFalse(ContactEducation.objects.filter(contact__user=self.user).exists())
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
