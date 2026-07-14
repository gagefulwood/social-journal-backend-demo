from collections import Counter
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Concat
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
from journals.models import Exercise, ExerciseStep, Log, Reflection
from lookups.models import (
    ContextCategory,
    FactCategory,
    InteractionMode,
    Mood,
    ObservationMarker,
    Relation,
)
from users.models import Users


CONTACTS = (
    {
        "first_name": "Alex",
        "last_name": "Rivera",
        "email": "alex.rivera@example.com",
        "legacy_seed_emails": ("alex.rivera.demo@example.com",),
        "phone_number": "+1 555-0101",
        "relation": "Friend",
        "company": "Northstar Studio",
        "profile_fields": {
            "gender_identity": "Man",
            "pronouns": "He/him",
            "birthday": date(1999, 5, 19),
            "timezone": "America/Chicago",
            "first_met_date": date(2024, 7, 9),
            "met_through": "University",
            "met_location": "Starkville, MS",
        },
        "profile": {
            "contact_methods": (
                {
                    "kind": "email",
                    "label": "Primary email",
                    "value": "alex.rivera@example.com",
                    "is_primary": True,
                },
                {
                    "kind": "phone",
                    "label": "Mobile",
                    "value": "+1 555-0101",
                    "is_primary": True,
                },
            ),
            "addresses": (
                {
                    "label": "Home",
                    "line_1": "210 College View Dr",
                    "city": "Starkville",
                    "region": "MS",
                    "postal_code": "39759",
                    "country_code": "US",
                    "is_primary": True,
                },
            ),
            "employment": (
                {
                    "title": "Product designer",
                    "organization": "Northstar Studio",
                    "is_current": True,
                },
            ),
            "education": (
                {
                    "credential": "B.S.",
                    "field_of_study": "Computer Science",
                    "institution": "Mississippi State University",
                    "is_current": False,
                },
            ),
        },
        "facts": (
            {
                "category": "Preferences",
                "label": "Coffee",
                "value": "Oat milk",
                "legacy_values": ("Coffee: Oat milk", "Prefers oat milk in coffee"),
                "is_conversation_cue": True,
            },
            {
                "category": "Routines & goals",
                "label": "Training",
                "value": "Spring 10K",
                "legacy_values": ("Training: Spring 10K", "Training for a spring 10K"),
                "is_conversation_cue": True,
            },
            {
                "category": "Work & school",
                "label": "Project",
                "value": "Product launch",
                "legacy_values": ("Project: Product launch",),
            },
            {
                "category": "Important dates",
                "label": "Birthday",
                "value": "May 19",
                "legacy_values": ("July 18", "Birthday: July 18"),
            },
        ),
        "observations": (
            {
                "body": "Ask how the new project launch went.",
                "event_title": "Demo: Coffee catch-up with Alex",
                "marker": "Important",
                "observation_type": "conversation_cue",
                "status": "current",
            },
            {
                "body": "Alex seemed energized about the project.",
                "event_title": "Demo: Coffee catch-up with Alex",
                "marker": "General",
                "observation_type": "notice",
                "status": "revisit_later",
            },
            {
                "body": "They made time to check in during a busy week.",
                "event_title": "Demo: Video catch-up with Alex",
                "marker": "Important",
                "observation_type": "appreciation",
                "status": "current",
            },
            {
                "body": "Mentioned exploring a weekend hiking trip.",
                "event_title": "Demo: Video catch-up with Alex",
                "marker": "General",
                "observation_type": "change",
                "status": "archived",
            },
        ),
    },
    {
        "first_name": "Jordan",
        "last_name": "Lee",
        "email": "jordan.lee.demo@example.com",
        "phone_number": "+1-555-0102",
        "relation": "Coworker",
        "company": "Acme Labs",
        "address": "88 Legacy Lane, Columbus, OH 43215",
        "facts": (
            {
                "category": "Preferences",
                "label": "Music",
                "value": "Small live venues",
                "legacy_values": ("Music: Small live venues", "Enjoys small live-music venues"),
            },
        ),
        "observations": (
            {
                "body": "Mentioned wanting feedback on a presentation.",
                "event_title": "Demo: Team lunch with Jordan",
                "marker": "General",
                "observation_type": "notice",
                "status": "current",
            },
        ),
    },
    {
        "first_name": "Priya",
        "last_name": "Shah",
        "email": "priya.shah.demo@example.com",
        "phone_number": "+1-555-0103",
        "relation": "Friend",
        "company": "Civic Works",
        "profile_fields": {
            "preferred_name": "Priya",
        },
        "profile": {
            "contact_methods": (
                {
                    "kind": "email",
                    "label": "Primary email",
                    "value": "priya.shah.demo@example.com",
                    "is_primary": True,
                },
            ),
        },
        "facts": (
            {
                "category": "Important dates",
                "label": "Birthday",
                "value": "October 12",
                "legacy_values": ("Birthday: October 12", "Birthday is in October"),
            },
            {
                "category": "Routines & goals",
                "label": "Hiking",
                "value": "Trail weekends",
                "legacy_values": ("Hiking: Trail weekends", "Likes trail hiking"),
            },
        ),
        "observations": (
            {
                "body": "Send the photos from the last hike.",
                "event_title": "Demo: Weekend hike with Priya",
                "marker": "Important",
                "observation_type": "appreciation",
                "status": "current",
            },
        ),
    },
    {
        "first_name": "Marcus",
        "last_name": "Chen",
        "email": "marcus.chen.demo@example.com",
        "phone_number": "+1-555-0104",
        "relation": "Mentor",
        "company": "Independent",
        "profile": {
            "contact_methods": (
                {
                    "kind": "email",
                    "label": "Personal email",
                    "value": "marcus.chen.demo@example.com",
                    "is_primary": True,
                },
                {
                    "kind": "email",
                    "label": "Work email",
                    "value": "marcus@advisory.example",
                    "is_primary": False,
                },
                {
                    "kind": "phone",
                    "label": "Mobile",
                    "value": "+1-555-0104",
                    "is_primary": True,
                },
                {
                    "kind": "phone",
                    "label": "Office",
                    "value": "+1 555-0194",
                    "is_primary": False,
                },
            ),
            "addresses": (
                {
                    "label": "Home",
                    "line_1": "14 Cypress Way",
                    "city": "Austin",
                    "region": "TX",
                    "postal_code": "78701",
                    "country_code": "US",
                    "is_primary": True,
                },
                {
                    "label": "Office",
                    "line_1": "600 Congress Ave",
                    "line_2": "Suite 1200",
                    "city": "Austin",
                    "region": "TX",
                    "postal_code": "78701",
                    "country_code": "US",
                    "is_primary": False,
                },
            ),
            "employment": (
                {
                    "title": "Independent advisor",
                    "organization": "Chen Advisory",
                    "is_current": True,
                },
                {
                    "title": "Engineering director",
                    "organization": "Lone Star Systems",
                    "start_date": date(2016, 2, 1),
                    "end_date": date(2022, 8, 31),
                    "is_current": False,
                },
            ),
            "education": (
                {
                    "credential": "M.B.A.",
                    "institution": "University of Texas at Austin",
                    "is_current": False,
                },
                {
                    "credential": "B.S.",
                    "field_of_study": "Electrical Engineering",
                    "institution": "Rice University",
                    "is_current": False,
                },
            ),
        },
        "facts": (
            {
                "category": "Practical details",
                "label": "Availability",
                "value": "Friday afternoons",
                "legacy_values": ("Availability: Friday afternoons", "Usually available on Friday afternoons"),
                "is_conversation_cue": True,
            },
        ),
        "observations": (
            {
                "body": "Follow up on the book recommendation.",
                "event_title": "Demo: Career advice call with Marcus",
                "marker": "General",
                "observation_type": "conversation_cue",
                "status": "current",
            },
        ),
    },
    {
        "first_name": "Elena",
        "last_name": "Torres",
        "email": "elena.torres.demo@example.com",
        "phone_number": "+1-555-0105",
        "relation": "Family",
        "company": "",
        "facts": (
            {
                "category": "Family & relationships",
                "label": "Dinner",
                "value": "First Sunday of each month",
                "legacy_values": ("Dinner: First Sunday of each month", "Makes a family dinner on the first Sunday each month"),
            },
        ),
        "observations": (
            {
                "body": "Ask for the soup recipe.",
                "event_title": "Demo: Family dinner with Elena",
                "marker": "Important",
                "observation_type": "conversation_cue",
                "status": "current",
            },
        ),
    },
)


FACT_CATEGORY_SPECS = (
    ("Preferences", "FiHeart"),
    ("Routines & goals", "FiCompass"),
    ("Work & school", "FiBriefcase"),
    ("Important dates", "FiCalendar"),
    ("Family & relationships", "FiUsers"),
    ("Practical details", "FiClipboard"),
)


OBSERVATION_MARKER_SPECS = {
    "General": {"color_hex": "#718096", "icon_reference": "FiFileText"},
    "Important": {"color_hex": "#E53E3E", "icon_reference": "FiAlertCircle"},
}


PINNED_FACT_SPECS = (
    {
        "contact": "alex.rivera@example.com",
        "label": "Coffee",
        "event_title": "Demo: Coffee catch-up with Alex",
        "offset_hours": 3,
    },
    {
        "contact": "alex.rivera@example.com",
        "label": "Training",
        "event_title": "Demo: Coffee catch-up with Alex",
        "offset_hours": 2,
    },
    {
        "contact": "alex.rivera@example.com",
        "label": "Project",
        "event_title": "Demo: Coffee catch-up with Alex",
        "offset_hours": 1,
    },
)


PINNED_OBSERVATION_SPECS = (
    {
        "contact": "alex.rivera@example.com",
        "body": "Ask how the new project launch went.",
        "event_title": "Demo: Coffee catch-up with Alex",
        "offset_hours": 3,
    },
    {
        "contact": "alex.rivera@example.com",
        "body": "Alex seemed energized about the project.",
        "event_title": "Demo: Coffee catch-up with Alex",
        "offset_hours": 2,
    },
    {
        "contact": "alex.rivera@example.com",
        "body": "They made time to check in during a busy week.",
        "event_title": "Demo: Video catch-up with Alex",
        "offset_hours": 1,
    },
)


EVENTS = (
    {
        "title": "Demo: Coffee catch-up with Alex",
        "days": -5,
        "contact": "alex.rivera@example.com",
        "context": "Social",
        "mode": "In person",
        "mood": "Happy",
        "location": "Corner Coffee",
        "impact": "positive",
    },
    {
        "title": "Demo: Team lunch with Jordan",
        "days": -12,
        "contact": "jordan.lee.demo@example.com",
        "context": "Professional",
        "mode": "In person",
        "mood": "Neutral",
        "location": "Market Hall",
        "impact": "neutral",
    },
    {
        "title": "Demo: Weekend hike with Priya",
        "days": -22,
        "contact": "priya.shah.demo@example.com",
        "context": "Social",
        "mode": "In person",
        "mood": "Happy",
        "location": "Cedar Ridge Trail",
        "tier": "milestone",
        "impact": "positive",
    },
    {
        "title": "Demo: Career advice call with Marcus",
        "days": -38,
        "contact": "marcus.chen.demo@example.com",
        "context": "Professional",
        "mode": "Phone call",
        "mood": "Neutral",
        "location": "",
        "impact": "positive",
    },
    {
        "title": "Demo: Family dinner with Elena",
        "days": -55,
        "contact": "elena.torres.demo@example.com",
        "context": "Family",
        "mode": "In person",
        "mood": "Happy",
        "location": "Elena's home",
        "impact": "positive",
    },
    {
        "title": "Demo: Video catch-up with Alex",
        "days": -68,
        "contact": "alex.rivera@example.com",
        "context": "Social",
        "mode": "Video call",
        "mood": "Neutral",
        "location": "",
        "impact": "neutral",
    },
    {
        "title": "Demo: Planning session with Jordan",
        "days": 7,
        "contact": "jordan.lee.demo@example.com",
        "context": "Professional",
        "mode": "Video call",
        "mood": None,
        "location": "",
        "impact": "",
    },
    {
        "title": "Demo: Birthday brunch with Priya",
        "days": -90,
        "contact": "priya.shah.demo@example.com",
        "context": "Social",
        "mode": "In person",
        "mood": "Happy",
        "location": "The Garden Room",
        "tier": "milestone",
        "impact": "positive",
    },
)


HISTORICAL_MONTH_COUNT = 4
HISTORICAL_EVENT_PATTERNS = (
    {
        "title": "Coffee check-in with Alex",
        "contact": "alex.rivera@example.com",
        "context": "Social",
        "mode": "In person",
        "mood": "Happy",
        "location": "Corner Coffee",
        "impact": "positive",
        "description": "Caught up over coffee and traded updates from the week.",
    },
    {
        "title": "Project sync with Jordan",
        "contact": "jordan.lee.demo@example.com",
        "context": "Professional",
        "mode": "Video call",
        "mood": "Neutral",
        "location": "",
        "impact": "positive",
        "description": "Compared project notes and agreed on the next small step.",
    },
    {
        "title": "Trail walk with Priya",
        "contact": "priya.shah.demo@example.com",
        "context": "Social",
        "mode": "In person",
        "mood": "Happy",
        "location": "Cedar Ridge Trail",
        "impact": "positive",
        "description": "Took an easy trail walk and caught up without rushing.",
    },
    {
        "title": "Advice call with Marcus",
        "contact": "marcus.chen.demo@example.com",
        "context": "Professional",
        "mode": "Phone call",
        "mood": "Neutral",
        "location": "",
        "impact": "positive",
        "description": "Talked through a decision and left with a clearer question.",
    },
    {
        "title": "Family lunch with Elena",
        "contact": "elena.torres.demo@example.com",
        "context": "Family",
        "mode": "In person",
        "mood": "Happy",
        "location": "Elena's home",
        "impact": "positive",
        "description": "Shared lunch and lingered over familiar family stories.",
    },
    {
        "title": "Video catch-up with Alex",
        "contact": "alex.rivera@example.com",
        "context": "Social",
        "mode": "Video call",
        "mood": "Neutral",
        "location": "",
        "impact": "neutral",
        "description": "Made time for a short video check-in during a busy week.",
    },
    {
        "title": "Team coffee with Jordan",
        "contact": "jordan.lee.demo@example.com",
        "context": "Professional",
        "mode": "In person",
        "mood": "Happy",
        "location": "Market Hall",
        "impact": "positive",
        "description": "Stepped away from work for coffee and a relaxed conversation.",
    },
    {
        "title": "Planning the next hike with Priya",
        "contact": "priya.shah.demo@example.com",
        "context": "Social",
        "mode": "Phone call",
        "mood": "Happy",
        "location": "",
        "impact": "positive",
        "description": "Compared trail ideas and picked a weekend to keep open.",
    },
    {
        "title": "Book discussion with Marcus",
        "contact": "marcus.chen.demo@example.com",
        "context": "Professional",
        "mode": "Video call",
        "mood": "Happy",
        "location": "",
        "impact": "positive",
        "description": "Discussed a recent book and the questions it brought up.",
    },
    {
        "title": "Recipe swap with Elena",
        "contact": "elena.torres.demo@example.com",
        "context": "Family",
        "mode": "Phone call",
        "mood": "Happy",
        "location": "",
        "impact": "positive",
        "description": "Compared notes on a family recipe and planned the next meal.",
    },
)


def event_specs():
    yield from EVENTS

    for month_number in range(1, HISTORICAL_MONTH_COUNT + 1):
        for event_number, pattern in enumerate(HISTORICAL_EVENT_PATTERNS, start=1):
            days_ago = (month_number - 1) * 30 + event_number * 3
            yield {
                **pattern,
                "title": f'Demo history M{month_number}: {pattern["title"]}',
                "days": -days_ago,
            }


class Command(BaseCommand):
    help = "Add idempotent demo contacts, events, and journal entries to an existing account."

    def add_arguments(self, parser):
        parser.add_argument(
            "user_name",
            help="Exact username, email address, or full name of an existing user.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created, then roll back all changes.",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options["user_name"])
        dry_run = options["dry_run"]

        with transaction.atomic():
            created = self._populate(user)
            if dry_run:
                transaction.set_rollback(True)

        verb = "Would create" if dry_run else "Created"
        summary = ", ".join(
            f"{count} {label}"
            for label, count in sorted(created.items())
            if count
        )
        if not summary:
            summary = "no records; this account already has the demo dataset"

        self.stdout.write(
            self.style.SUCCESS(f"{verb} {summary} for {user.username} ({user.email}).")
        )

    def _resolve_user(self, raw_selector):
        selector = " ".join(raw_selector.split())
        if not selector:
            raise CommandError("Provide a username, email address, or full name.")

        matches = Users.objects.annotate(
            full_name=Concat("first_name", Value(" "), "last_name")
        ).filter(
            Q(username__iexact=selector)
            | Q(email__iexact=selector)
            | Q(full_name__iexact=selector)
        )
        users = list(matches.order_by("id")[:2])

        if not users:
            raise CommandError(f'No user matched "{selector}".')
        if len(users) > 1:
            raise CommandError(
                f'More than one user matched "{selector}". Use an exact username or email.'
            )
        return users[0]

    def _populate(self, user):
        created = Counter()
        categories = self._create_fact_categories(user, created)
        markers = self._get_observation_markers(user, created)
        contacts = self._create_contacts(user, categories, created)
        events = self._create_events(user, contacts, created)
        self._create_observations(contacts, events, markers, created)
        self._pin_context(contacts, events)
        self._create_journals(user, events, created)
        return created

    def _create_fact_categories(self, user, created):
        categories = {}
        for name, icon_reference in FACT_CATEGORY_SPECS:
            category, was_created = FactCategory.objects.get_or_create(
                user=user,
                parent=None,
                name=name,
                defaults={"icon_reference": icon_reference},
            )
            created["fact categories"] += was_created
            categories[name] = category
        return categories

    def _get_observation_markers(self, user, created):
        markers = {}
        for name, defaults in OBSERVATION_MARKER_SPECS.items():
            marker = ObservationMarker.objects.filter(
                is_system_default=True,
                name=name,
            ).first()
            if marker is None:
                marker, was_created = ObservationMarker.objects.get_or_create(
                    user=user,
                    name=name,
                    defaults=defaults,
                )
                created["observation markers"] += was_created
            markers[name] = marker
        return markers

    def _create_contacts(self, user, categories, created):
        contacts = {}

        for spec in CONTACTS:
            relation = self._lookup(Relation, spec["relation"])
            contact = Contact.objects.filter(
                user=user,
                email=spec["email"],
            ).first()
            if contact is None:
                contact = Contact.objects.filter(
                    user=user,
                    email__in=spec.get("legacy_seed_emails", ()),
                ).order_by("id").first()

            was_created = contact is None
            if contact is None:
                contact = Contact(
                    user=user,
                    first_name=spec["first_name"],
                    last_name=spec["last_name"],
                    first_met_date=timezone.localdate() - timedelta(days=730),
                )

            desired_fields = {
                "first_name": spec["first_name"],
                "last_name": spec["last_name"],
                "email": spec["email"],
                "phone_number": spec["phone_number"],
                "relation": relation,
                "company": spec["company"],
                "address": spec.get("address", ""),
                **spec.get("profile_fields", {}),
            }
            changed_fields = []
            for field, value in desired_fields.items():
                current_value = (
                    getattr(contact, f"{field}_id")
                    if field == "relation"
                    else getattr(contact, field)
                )
                expected_value = (
                    value.id if field == "relation" and value is not None else value
                )
                if current_value != expected_value:
                    setattr(contact, field, value)
                    changed_fields.append(field)

            contact.full_clean()
            if was_created:
                contact.save()
            elif changed_fields:
                contact.save(update_fields=changed_fields)
            created["contacts"] += was_created
            contacts[spec["email"]] = contact

            self._sync_contact_profile(contact, spec.get("profile", {}), created)

            for fact_spec in spec["facts"]:
                self._upsert_fact(contact, fact_spec, categories, created)

        return contacts

    def _sync_contact_profile(self, contact, profile, created):
        if not profile:
            return

        method_specs = profile.get("contact_methods", ())
        for kind in (ContactMethod.KIND_EMAIL, ContactMethod.KIND_PHONE):
            primary_count = sum(
                spec["kind"] == kind and spec.get("is_primary", False)
                for spec in method_specs
            )
            if primary_count > 1:
                raise CommandError(
                    f"Demo profile for {contact} defines multiple primary {kind} methods."
                )
            if primary_count == 1:
                self._demote_existing_primaries(
                    contact.contact_methods.filter(kind=kind, is_primary=True)
                )

        address_specs = profile.get("addresses", ())
        if sum(spec.get("is_primary", False) for spec in address_specs) > 1:
            raise CommandError(
                f"Demo profile for {contact} defines multiple primary addresses."
            )
        if any(spec.get("is_primary", False) for spec in address_specs):
            self._demote_existing_primaries(contact.addresses.filter(is_primary=True))

        for spec in method_specs:
            self._upsert_profile_record(
                ContactMethod,
                contact,
                identity={"kind": spec["kind"], "label": spec.get("label", "")},
                values=spec,
                counter="contact methods",
                created=created,
            )
        for spec in address_specs:
            self._upsert_profile_record(
                ContactAddress,
                contact,
                identity={"label": spec.get("label", "")},
                values=spec,
                counter="addresses",
                created=created,
            )
        for spec in profile.get("employment", ()):
            self._upsert_profile_record(
                ContactEmployment,
                contact,
                identity={
                    "title": spec["title"],
                    "organization": spec.get("organization", ""),
                },
                values=spec,
                counter="employment records",
                created=created,
            )
        for spec in profile.get("education", ()):
            self._upsert_profile_record(
                ContactEducation,
                contact,
                identity={
                    "credential": spec.get("credential", ""),
                    "field_of_study": spec.get("field_of_study", ""),
                    "institution": spec["institution"],
                },
                values=spec,
                counter="education records",
                created=created,
            )

    def _demote_existing_primaries(self, queryset):
        for record in queryset:
            record.is_primary = False
            record.full_clean()
            record.save(update_fields=["is_primary"])

    def _upsert_profile_record(
        self,
        model,
        contact,
        *,
        identity,
        values,
        counter,
        created,
    ):
        matches = model.objects.filter(contact=contact, **identity).order_by("id")
        record = matches.first()
        was_created = record is None
        if record is None:
            record = model(contact=contact, **identity)

        for field, value in values.items():
            setattr(record, field, value)
        record.full_clean()
        record.save()
        created[counter] += was_created

        # Only exact duplicate rows matching the stable script identity are owned
        # by this fixture and safe to retire.
        if not was_created:
            matches.exclude(pk=record.pk).delete()

    def _upsert_fact(self, contact, fact_spec, categories, created):
        value = fact_spec["value"]
        label = fact_spec["label"]
        existing_values = (value, *fact_spec.get("legacy_values", ()))
        category = categories[fact_spec["category"]]
        fact = Fact.objects.filter(
            contact=contact,
            category=category,
            label=label,
        ).first() or Fact.objects.filter(
            contact=contact,
            detail_value__in=existing_values,
        ).order_by("id").first()
        is_conversation_cue = fact_spec.get("is_conversation_cue", False)

        if fact is None:
            Fact.objects.create(
                contact=contact,
                category=category,
                label=label,
                detail_value=value,
                is_conversation_cue=is_conversation_cue,
            )
            created["facts"] += 1
            return

        updates = []
        if fact.label != label:
            fact.label = label
            updates.append("label")
        if fact.detail_value != value:
            fact.detail_value = value
            updates.append("detail_value")
        if fact.category_id != category.id:
            fact.category = category
            updates.append("category")
        if fact.is_conversation_cue != is_conversation_cue:
            fact.is_conversation_cue = is_conversation_cue
            updates.append("is_conversation_cue")
        if updates:
            fact.save(update_fields=updates)

    def _create_observations(self, contacts, events, markers, created):
        events_by_title = {event.title: event for event in events}
        for spec in CONTACTS:
            contact = contacts[spec["email"]]
            for observation_spec in spec["observations"]:
                event = events_by_title[observation_spec["event_title"]]
                observation, was_created = Observation.objects.get_or_create(
                    contact=contact,
                    body=observation_spec["body"],
                    defaults={
                        "marker": markers[observation_spec["marker"]],
                        "observation_type": observation_spec["observation_type"],
                        "status": observation_spec["status"],
                        "occurred_at": event.event_timestamp,
                        "event": event,
                    },
                )
                created["observations"] += was_created
                if was_created:
                    continue

                updates = []
                for field, value in {
                    "marker": markers[observation_spec["marker"]],
                    "observation_type": observation_spec["observation_type"],
                    "status": observation_spec["status"],
                    "occurred_at": event.event_timestamp,
                    "event": event,
                }.items():
                    current_value = (
                        getattr(observation, f"{field}_id")
                        if field in {"marker", "event"}
                        else getattr(observation, field)
                    )
                    expected_value = value.id if field in {"marker", "event"} else value
                    if current_value != expected_value:
                        setattr(observation, field, value)
                        updates.append(field)
                if updates:
                    observation.save(update_fields=updates)

    def _pin_context(self, contacts, events):
        events_by_title = {event.title: event for event in events}

        for spec in PINNED_FACT_SPECS:
            pinned_at = (
                events_by_title[spec["event_title"]].event_timestamp
                + timedelta(hours=spec["offset_hours"])
            )
            Fact.objects.filter(
                contact=contacts[spec["contact"]],
                label=spec["label"],
            ).exclude(pinned_at=pinned_at).update(pinned_at=pinned_at)

        for spec in PINNED_OBSERVATION_SPECS:
            pinned_at = (
                events_by_title[spec["event_title"]].event_timestamp
                + timedelta(hours=spec["offset_hours"])
            )
            Observation.objects.filter(
                contact=contacts[spec["contact"]],
                body=spec["body"],
            ).exclude(pinned_at=pinned_at).update(pinned_at=pinned_at)

    def _create_events(self, user, contacts, created):
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        events = []

        for spec in event_specs():
            event, was_created = Event.objects.get_or_create(
                user=user,
                title=spec["title"],
                defaults={
                    "description": spec.get(
                        "description",
                        "Sample data created by populate_account.",
                    ),
                    "event_timestamp": now + timedelta(days=spec["days"]),
                    "location_label": spec["location"],
                    "tier": spec.get("tier", "routine"),
                    "impact": spec["impact"],
                    "context_category": self._lookup(
                        ContextCategory, spec["context"]
                    ),
                    "interaction_mode": self._lookup(
                        InteractionMode, spec["mode"]
                    ),
                    "mood": self._lookup(Mood, spec["mood"]),
                },
            )
            created["events"] += was_created
            events.append(event)

            _, was_created = EventParticipant.objects.get_or_create(
                event=event,
                contact=contacts[spec["contact"]],
            )
            created["participants"] += was_created

        return events

    def _create_journals(self, user, events, created):
        happy = self._lookup(Mood, "Happy")
        neutral = self._lookup(Mood, "Neutral")

        log_specs = (
            (0, "Demo: A good conversation", "We caught up and made time for another coffee soon.", happy),
            (1, "Demo: Useful team lunch", "We compared notes on the current project and clarified next steps.", neutral),
            (2, "Demo: A restorative afternoon", "The hike was an easy way to reconnect without rushing.", happy),
            (4, "Demo: Family dinner notes", "Dinner was warm, relaxed, and full of familiar stories.", happy),
        )
        for event_index, title, body, mood in log_specs:
            _, was_created = Log.objects.get_or_create(
                user=user,
                event=events[event_index],
                title=title,
                defaults={"body": body, "mood": mood},
            )
            created["logs"] += was_created

        reflection_specs = (
            (2, "Demo: What made the hike meaningful"),
            (3, "Demo: Notes from Marcus's advice"),
        )
        for event_index, title in reflection_specs:
            _, was_created = Reflection.objects.get_or_create(
                user=user,
                event=events[event_index],
                title=title,
                defaults={
                    "clarity_check": "Clear",
                    "data": {
                        "prompt": "What do I want to remember?",
                        "response": "Being attentive made the conversation feel unhurried.",
                    },
                },
            )
            created["reflections"] += was_created

        exercise_specs = (
            (1, "Demo: Prepare for a direct conversation", 3, 6),
            (5, "Demo: Notice and reframe assumptions", 4, 7),
        )
        for event_index, title, pre, post in exercise_specs:
            exercise, was_created = Exercise.objects.get_or_create(
                user=user,
                event=events[event_index],
                title=title,
                defaults={"pre_measurement": pre, "post_measurement": post},
            )
            created["exercises"] += was_created

            steps = (
                (1, "What am I assuming?", "I may be filling in details I do not know."),
                (2, "What can I ask directly?", "I can ask a simple, open question."),
            )
            for display_order, prompt, response in steps:
                _, was_created = ExerciseStep.objects.get_or_create(
                    exercise=exercise,
                    display_order=display_order,
                    defaults={"prompt": prompt, "response": response},
                )
                created["exercise steps"] += was_created

    def _lookup(self, model, name):
        if not name:
            return None
        return model.objects.filter(
            name=name,
            is_system_default=True,
        ).first()
