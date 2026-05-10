from django.test import TestCase

from journals.models import Exercise
from journals.serializers import ExerciseSerializer, LogSerializer
from lookups.models import EntryTag, Mood

from .factories import EventFactory, UserFactory


class JournalSerializerTests(TestCase):
    def test_log_serializer_accepts_writable_mood_and_tag_ids(self):
        user = UserFactory()
        event = EventFactory(user=user)
        mood = Mood.objects.create(user=user, name='Calm', emoji_icon='C')
        tag = EntryTag.objects.create(user=user, tag_name='Important')
        request = type('Request', (), {'user': user})()
        serializer = LogSerializer(
            data={
                'event': event.id,
                'title': 'Dinner',
                'body': 'Good conversation.',
                'mood_id': mood.id,
                'tag_ids': [tag.id],
                'data': {'episode': 'first'},
            },
            context={'request': request},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        log = serializer.save(user=user)
        self.assertEqual(log.mood, mood)
        self.assertEqual(list(log.tags.all()), [tag])
        self.assertEqual(log.data, {'episode': 'first'})

    def test_exercise_serializer_writes_steps_and_delta(self):
        user = UserFactory()
        event = EventFactory(user=user)
        serializer = ExerciseSerializer(
            data={
                'event': event.id,
                'title': 'Breathing exercise',
                'pre_measurement': 10,
                'post_measurement': 4,
                'steps': [
                    {
                        'display_order': 1,
                        'prompt': 'Name the thought.',
                        'response': 'I named it.',
                    }
                ],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        exercise = serializer.save(user=user)
        self.assertEqual(exercise.measurement_delta, -6)
        self.assertEqual(exercise.steps.count(), 1)
        self.assertEqual(
            ExerciseSerializer(exercise).data['measurement_delta'],
            -6,
        )

    def test_exercise_serializer_replaces_steps_on_update(self):
        user = UserFactory()
        event = EventFactory(user=user)
        exercise = Exercise.objects.create(
            user=user,
            event=event,
            title='Existing exercise',
            pre_measurement=1,
            post_measurement=2,
        )
        exercise.steps.create(
            display_order=1,
            prompt='Old prompt',
            response='Old response',
        )
        serializer = ExerciseSerializer(
            exercise,
            data={
                'steps': [
                    {
                        'display_order': 2,
                        'prompt': 'New prompt',
                        'response': 'New response',
                    }
                ]
            },
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertEqual(exercise.steps.count(), 1)
        self.assertEqual(exercise.steps.get().prompt, 'New prompt')
