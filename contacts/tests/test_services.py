from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from contacts.services import (
    calculate_connection_strength,
    calculate_interaction_diversity_score,
    calculate_interaction_frequency_score,
    calculate_relationship_trend,
    calculate_sentiment_score,
    calculate_sentiment_profile,
    normalize_mood_name,
)
from events.models import Event
from journals.models import Log
from lookups.models import ContextCategory, Mood

from .factories import ContactFactory, UserFactory


class ContactStatisticsServiceTests(TestCase):
    def test_frequency_uses_weighted_buckets_and_caps_at_100(self):
        now = timezone.now()
        events = [
            SimpleNamespace(event_timestamp=now - timedelta(days=3)),
            SimpleNamespace(event_timestamp=now - timedelta(days=20)),
            SimpleNamespace(event_timestamp=now - timedelta(days=70)),
            SimpleNamespace(event_timestamp=now - timedelta(days=120)),
        ]

        self.assertEqual(calculate_interaction_frequency_score(events, now=now), 60)

        frequent_events = [
            SimpleNamespace(event_timestamp=now - timedelta(days=1))
            for _ in range(5)
        ]
        self.assertEqual(
            calculate_interaction_frequency_score(frequent_events, now=now),
            100,
        )

    def test_relationship_trend_outcomes(self):
        now = timezone.now()

        self.assertEqual(calculate_relationship_trend([], now=now), "dormant")
        self.assertEqual(
            calculate_relationship_trend(
                [
                    SimpleNamespace(event_timestamp=now - timedelta(days=1)),
                    SimpleNamespace(event_timestamp=now - timedelta(days=45)),
                ],
                now=now,
            ),
            "stable",
        )
        self.assertEqual(
            calculate_relationship_trend(
                [
                    SimpleNamespace(event_timestamp=now - timedelta(days=1)),
                    SimpleNamespace(event_timestamp=now - timedelta(days=2)),
                    SimpleNamespace(event_timestamp=now - timedelta(days=45)),
                ],
                now=now,
            ),
            "growing",
        )
        self.assertEqual(
            calculate_relationship_trend(
                [
                    SimpleNamespace(event_timestamp=now - timedelta(days=1)),
                    SimpleNamespace(event_timestamp=now - timedelta(days=45)),
                    SimpleNamespace(event_timestamp=now - timedelta(days=46)),
                ],
                now=now,
            ),
            "fading",
        )

    def test_diversity_score_handles_zero_and_unique_categories(self):
        events = [
            SimpleNamespace(context_category_id=1),
            SimpleNamespace(context_category_id=1),
            SimpleNamespace(context_category_id=2),
            SimpleNamespace(context_category_id=None),
        ]

        self.assertEqual(calculate_interaction_diversity_score(events, 0), 0)
        self.assertEqual(calculate_interaction_diversity_score(events, 4), 50)

    def test_sentiment_profile_counts_log_moods_by_normalized_name(self):
        user = UserFactory()
        contact = ContactFactory(user=user)
        event = Event.objects.create(
            user=user,
            title="Dinner",
            event_timestamp=timezone.now(),
        )
        mood = Mood.objects.create(
            user=user,
            name="Very Happy",
            emoji_icon="VH",
            polarity=1,
        )
        Log.objects.create(
            user=user,
            event=event,
            title="Dinner",
            body="Good conversation.",
            mood=mood,
        )

        self.assertEqual(normalize_mood_name(" Very Happy "), "veryhappy")
        self.assertEqual(calculate_sentiment_profile([event]), {"veryhappy": 1})
        self.assertEqual(calculate_sentiment_score([event]), 100)

    def test_custom_moods_default_to_neutral_sentiment(self):
        user = UserFactory()
        event = Event.objects.create(
            user=user,
            title="Dinner",
            event_timestamp=timezone.now(),
        )
        mood = Mood.objects.create(user=user, name="Mixed", emoji_icon="M")
        Log.objects.create(
            user=user,
            event=event,
            title="Dinner",
            body="Complicated conversation.",
            mood=mood,
        )

        self.assertEqual(mood.polarity, 0)
        self.assertEqual(calculate_sentiment_score([event]), 50)

    def test_connection_strength_uses_equal_weights(self):
        score = calculate_connection_strength(
            interaction_frequency_score=60,
            relationship_trend="growing",
            interaction_diversity_score=40,
            sentiment_score=75,
        )

        self.assertEqual(score, 69)
