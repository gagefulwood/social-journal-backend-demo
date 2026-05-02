from django.test import TestCase

from lookups.models import Mood
from lookups.serializers import MoodSerializer


class MoodModelTests(TestCase):
    def test_polarity_defaults_to_neutral(self):
        mood = Mood.objects.create(name="Mixed", emoji_icon="M")

        self.assertEqual(mood.polarity, 0)

    def test_polarity_choices_include_positive_neutral_negative(self):
        choices = dict(Mood._meta.get_field("polarity").choices)

        self.assertEqual(choices[1], "Positive")
        self.assertEqual(choices[0], "Neutral")
        self.assertEqual(choices[-1], "Negative")


class MoodSerializerTests(TestCase):
    def test_serializer_exposes_polarity(self):
        mood = Mood.objects.create(name="Happy", emoji_icon="H", polarity=1)

        self.assertEqual(MoodSerializer(mood).data["polarity"], 1)
