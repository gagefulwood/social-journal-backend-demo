from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.utils import timezone

from contacts.models import Contact, Fact, Observation
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
        "email": "alex.rivera.demo@example.com",
        "phone_number": "+1-555-0101",
        "relation": "Friend",
        "company": "Northstar Studio",
        "facts": ("Prefers oat milk in coffee", "Training for a spring 10K"),
        "observations": ("Ask how the new project launch went.",),
    },
    {
        "first_name": "Jordan",
        "last_name": "Lee",
        "email": "jordan.lee.demo@example.com",
        "phone_number": "+1-555-0102",
        "relation": "Coworker",
        "company": "Acme Labs",
        "facts": ("Enjoys small live-music venues",),
        "observations": ("Mentioned wanting feedback on a presentation.",),
    },
    {
        "first_name": "Priya",
        "last_name": "Shah",
        "email": "priya.shah.demo@example.com",
        "phone_number": "+1-555-0103",
        "relation": "Friend",
        "company": "Civic Works",
        "facts": ("Birthday is in October", "Likes trail hiking"),
        "observations": ("Send the photos from the last hike.",),
    },
    {
        "first_name": "Marcus",
        "last_name": "Chen",
        "email": "marcus.chen.demo@example.com",
        "phone_number": "+1-555-0104",
        "relation": "Mentor",
        "company": "Independent",
        "facts": ("Usually available on Friday afternoons",),
        "observations": ("Follow up on the book recommendation.",),
    },
    {
        "first_name": "Elena",
        "last_name": "Torres",
        "email": "elena.torres.demo@example.com",
        "phone_number": "+1-555-0105",
        "relation": "Family",
        "company": "",
        "facts": ("Makes a family dinner on the first Sunday each month",),
        "observations": ("Ask for the soup recipe.",),
    },
)


EVENTS = (
    {
        "title": "Demo: Coffee catch-up with Alex",
        "days": -5,
        "contact": "alex.rivera.demo@example.com",
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
        "contact": "alex.rivera.demo@example.com",
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
        contacts = self._create_contacts(user, created)
        events = self._create_events(user, contacts, created)
        self._create_journals(user, events, created)
        return created

    def _create_contacts(self, user, created):
        fact_category = FactCategory.objects.filter(is_system_default=True).first()
        observation_marker = ObservationMarker.objects.filter(
            is_system_default=True
        ).first()
        contacts = {}

        for spec in CONTACTS:
            relation = self._lookup(Relation, spec["relation"])
            contact, was_created = Contact.objects.get_or_create(
                user=user,
                email=spec["email"],
                defaults={
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "phone_number": spec["phone_number"],
                    "relation": relation,
                    "company": spec["company"],
                    "first_met_date": timezone.localdate() - timedelta(days=730),
                },
            )
            created["contacts"] += was_created
            contacts[spec["email"]] = contact

            for value in spec["facts"]:
                _, was_created = Fact.objects.get_or_create(
                    contact=contact,
                    detail_value=value,
                    defaults={"category": fact_category},
                )
                created["facts"] += was_created

            for body in spec["observations"]:
                _, was_created = Observation.objects.get_or_create(
                    contact=contact,
                    body=body,
                    defaults={"marker": observation_marker},
                )
                created["observations"] += was_created

        return contacts

    def _create_events(self, user, contacts, created):
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        events = []

        for spec in EVENTS:
            event, was_created = Event.objects.get_or_create(
                user=user,
                title=spec["title"],
                defaults={
                    "description": "Sample data created by populate_account.",
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
