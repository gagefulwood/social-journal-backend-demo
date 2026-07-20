from datetime import date, timedelta
from io import StringIO
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count
from django.test import TestCase, override_settings
from django.utils import timezone

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
from journals.models import Log, Reflection, ReflectionAttachment, ReflectionContact
from journals.services import completion_errors
from lookups.models import FactCategory
from media.models import MediaAsset
from users.models import Users


class PopulateAccountCommandTests(TestCase):
    anchor = date(2026, 7, 17)

    def setUp(self):
        self.user = Users.objects.create_user(
            email="gage@example.com",
            username="gage",
            first_name="Gage",
            last_name="Fulwood",
            password="test-password",
        )

    def reset(self, user=None):
        target = user or self.user
        output = StringIO()
        call_command(
            "populate_account",
            target.username,
            reset_demo_data=True,
            confirm_reset=True,
            anchor_date=self.anchor.isoformat(),
            stdout=output,
        )
        return output.getvalue()

    def test_default_and_explicit_dry_runs_make_no_writes(self):
        existing = Contact.objects.create(
            user=self.user,
            first_name="Existing",
            last_name="Contact",
            email="existing@example.com",
        )
        before = {
            "contacts": Contact.objects.filter(user=self.user).count(),
            "events": Event.objects.filter(user=self.user).count(),
            "categories": FactCategory.objects.filter(user=self.user).count(),
        }

        default_output = StringIO()
        call_command(
            "populate_account",
            self.user.username,
            anchor_date=self.anchor.isoformat(),
            stdout=default_output,
        )
        explicit_output = StringIO()
        call_command(
            "populate_account",
            self.user.username,
            dry_run=True,
            anchor_date=self.anchor.isoformat(),
            stdout=explicit_output,
        )

        self.assertTrue(Contact.objects.filter(pk=existing.pk).exists())
        self.assertEqual(
            before,
            {
                "contacts": Contact.objects.filter(user=self.user).count(),
                "events": Event.objects.filter(user=self.user).count(),
                "categories": FactCategory.objects.filter(user=self.user).count(),
            },
        )
        self.assertIn("Would delete", default_output.getvalue())
        self.assertIn("would create", default_output.getvalue())
        self.assertIn("Would delete", explicit_output.getvalue())

    def test_reset_requires_both_confirmation_flags(self):
        for options in (
            {"reset_demo_data": True},
            {"confirm_reset": True},
            {
                "dry_run": True,
                "reset_demo_data": True,
                "confirm_reset": True,
            },
        ):
            with self.subTest(options=options):
                with self.assertRaises(CommandError):
                    call_command(
                        "populate_account",
                        self.user.username,
                        anchor_date=self.anchor.isoformat(),
                        stdout=StringIO(),
                        **options,
                    )

        self.assertFalse(Contact.objects.filter(user=self.user).exists())

    def test_reset_only_replaces_target_domain_data_and_preserves_reference_data(self):
        other = Users.objects.create_user(
            email="other@example.com",
            username="other",
            password="test-password",
            first_name="Other",
            last_name="User",
        )
        target_contact = Contact.objects.create(
            user=self.user,
            first_name="Old",
            last_name="Target",
            email="old-target@example.com",
        )
        other_contact = Contact.objects.create(
            user=other,
            first_name="Other",
            last_name="Contact",
            email="other-contact@example.com",
        )
        target_event = Event.objects.create(
            user=self.user,
            title="Old target event",
            event_timestamp=timezone.now(),
        )
        other_event = Event.objects.create(
            user=other,
            title="Other user event",
            event_timestamp=timezone.now(),
        )
        EventParticipant.objects.create(event=target_event, contact=target_contact)
        EventParticipant.objects.create(event=other_event, contact=other_contact)
        other_log = Log.objects.create(
            user=other,
            title="Other user log",
            format=Log.FORMAT_EPISODE,
            status="draft",
        )
        other_reflection = Reflection.objects.create(
            user=other,
            title="Other user reflection",
            format=Reflection.FORMAT_FREE,
            status="draft",
        )
        category = FactCategory.objects.create(
            user=self.user,
            name="Preserved category",
        )
        asset = MediaAsset.objects.create(
            user=self.user,
            file="media/demo-journal-photo.jpg",
            original_filename="demo-journal-photo.jpg",
            content_type="image/jpeg",
            file_size=24,
        )

        self.reset()

        self.assertFalse(Contact.objects.filter(pk=target_contact.pk).exists())
        self.assertFalse(Event.objects.filter(pk=target_event.pk).exists())
        self.assertTrue(Contact.objects.filter(pk=other_contact.pk).exists())
        self.assertTrue(Event.objects.filter(pk=other_event.pk).exists())
        self.assertTrue(Log.objects.filter(pk=other_log.pk).exists())
        self.assertTrue(Reflection.objects.filter(pk=other_reflection.pk).exists())
        self.assertTrue(FactCategory.objects.filter(pk=category.pk).exists())
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertEqual(Users.objects.count(), 2)
        self.assertFalse(
            ReflectionAttachment.objects.filter(
                reflection__user=self.user,
                media_asset=asset,
            ).exists()
        )

    def test_reset_reuses_demo_media_only_when_storage_bytes_exist(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            asset = MediaAsset.objects.create(
                user=self.user,
                file=SimpleUploadedFile(
                    "demo-journal-photo.jpg",
                    b"stored-demo-bytes",
                    content_type="image/jpeg",
                ),
                original_filename="demo-journal-photo.jpg",
                content_type="image/jpeg",
                file_size=len(b"stored-demo-bytes"),
            )

            self.reset()

            self.assertTrue(
                ReflectionAttachment.objects.filter(
                    reflection__user=self.user,
                    media_asset=asset,
                ).exists()
            )

    def test_populates_exact_counts_and_rich_contact_profiles(self):
        self.reset()

        self.assertEqual(Contact.objects.filter(user=self.user).count(), 8)
        self.assertEqual(Event.objects.filter(user=self.user).count(), 28)
        self.assertEqual(Fact.objects.filter(contact__user=self.user).count(), 32)
        self.assertEqual(Observation.objects.filter(contact__user=self.user).count(), 24)
        self.assertEqual(Log.objects.filter(user=self.user).count(), 14)
        self.assertEqual(Reflection.objects.filter(user=self.user).count(), 14)
        self.assertEqual(
            Log.objects.filter(user=self.user, status="completed").count()
            + Reflection.objects.filter(user=self.user, status="completed").count(),
            21,
        )
        self.assertEqual(
            Log.objects.filter(user=self.user, status="draft").count()
            + Reflection.objects.filter(user=self.user, status="draft").count(),
            7,
        )
        self.assertGreaterEqual(
            ContactMethod.objects.filter(contact__user=self.user).count(),
            10,
        )
        self.assertGreaterEqual(
            ContactAddress.objects.filter(contact__user=self.user).count(),
            6,
        )
        self.assertGreaterEqual(
            ContactEmployment.objects.filter(contact__user=self.user).count(),
            7,
        )
        self.assertGreaterEqual(
            ContactEducation.objects.filter(contact__user=self.user).count(),
            7,
        )
        for contact in Contact.objects.filter(user=self.user):
            for kind in (ContactMethod.KIND_EMAIL, ContactMethod.KIND_PHONE):
                self.assertLessEqual(
                    contact.contact_methods.filter(kind=kind, is_primary=True).count(),
                    1,
                )
            self.assertLessEqual(contact.addresses.filter(is_primary=True).count(), 1)

    def test_events_cover_exactly_sixty_calendar_days(self):
        self.reset()

        local_dates = [
            timezone.localdate(timestamp)
            for timestamp in Event.objects.filter(user=self.user).values_list(
                "event_timestamp",
                flat=True,
            )
        ]
        self.assertEqual(min(local_dates), self.anchor - timedelta(days=59))
        self.assertEqual(max(local_dates), self.anchor)
        self.assertTrue(
            all(
                self.anchor - timedelta(days=59) <= value <= self.anchor
                for value in local_dates
            )
        )

    def test_seeds_all_structured_journal_formats_without_generic_values(self):
        self.reset()

        self.assertEqual(
            set(Log.objects.filter(user=self.user).values_list("format", flat=True)),
            {
                Log.FORMAT_EPISODE,
                Log.FORMAT_SOCIAL_ENERGY,
                Log.FORMAT_SENTIMENT,
            },
        )
        self.assertEqual(
            set(
                Reflection.objects.filter(user=self.user).values_list(
                    "format",
                    flat=True,
                )
            ),
            {
                Reflection.FORMAT_INTERACTION,
                Reflection.FORMAT_MOMENT,
                Reflection.FORMAT_EMOTIONAL,
                Reflection.FORMAT_FREE,
            },
        )
        self.assertFalse(
            Log.objects.filter(
                user=self.user,
                format__in=["", "log", "Log", "legacy"],
            ).exists()
        )
        self.assertFalse(
            Reflection.objects.filter(
                user=self.user,
                format__in=["", "reflection", "Reflection", "legacy"],
            ).exists()
        )
        self.assertGreaterEqual(
            Log.objects.filter(
                user=self.user,
                format=Log.FORMAT_SENTIMENT,
                status="completed",
            ).count(),
            5,
        )

    def test_seeded_links_are_owned_and_valid(self):
        self.reset()

        events = Event.objects.filter(user=self.user)
        self.assertFalse(events.filter(participants__isnull=True).exists())
        group_event_ids = (
            EventParticipant.objects.filter(event__user=self.user)
            .values("event")
            .annotate(participant_count=Count("id"))
            .filter(participant_count__gte=2)
        )
        self.assertTrue(group_event_ids.exists())
        for participant in EventParticipant.objects.filter(event__user=self.user):
            self.assertEqual(participant.contact.user_id, self.user.id)
        for observation in Observation.objects.filter(contact__user=self.user):
            self.assertIsNotNone(observation.event_id)
            self.assertEqual(observation.event.user_id, self.user.id)
            self.assertTrue(
                EventParticipant.objects.filter(
                    event=observation.event,
                    contact=observation.contact,
                ).exists()
            )
        for journal in (
            list(Log.objects.filter(user=self.user))
            + list(Reflection.objects.filter(user=self.user))
        ):
            if journal.event_id:
                self.assertEqual(journal.event.user_id, self.user.id)
            if journal.primary_contact_id:
                self.assertEqual(journal.primary_contact.user_id, self.user.id)
        for link in ReflectionContact.objects.filter(reflection__user=self.user):
            self.assertEqual(link.contact.user_id, self.user.id)
        self.assertTrue(
            Log.objects.filter(user=self.user, event__isnull=False).exists()
        )
        self.assertTrue(
            Reflection.objects.filter(user=self.user, event__isnull=False).exists()
        )

    def test_completed_journal_payloads_are_valid(self):
        self.reset()

        completed = [
            *Log.objects.filter(user=self.user, status="completed"),
            *Reflection.objects.filter(user=self.user, status="completed"),
        ]
        self.assertEqual(len(completed), 21)
        for journal in completed:
            self.assertEqual(completion_errors(journal), {})
