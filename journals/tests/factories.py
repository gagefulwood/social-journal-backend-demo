import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from events.models import Event
from journals.models import Log, Reflection
from users.models import Users


class UserFactory(DjangoModelFactory):
    class Meta:
        model = Users
        django_get_or_create = ('email',)

    email = factory.Sequence(lambda n: f'journal-user{n}@example.com')
    username = factory.Sequence(lambda n: f'journal-user{n}')
    first_name = 'Journal'
    last_name = 'User'
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        raw_password = extracted or 'password123'
        self.set_password(raw_password)
        if create:
            self.save()


class EventFactory(DjangoModelFactory):
    class Meta:
        model = Event

    user = factory.SubFactory(UserFactory)
    title = factory.Sequence(lambda n: f'Event {n}')
    event_timestamp = factory.LazyFunction(timezone.now)


class LogFactory(DjangoModelFactory):
    class Meta:
        model = Log

    user = factory.SubFactory(UserFactory)
    event = factory.SubFactory(EventFactory, user=factory.SelfAttribute('..user'))
    title = factory.Sequence(lambda n: f'Log {n}')
    body = 'A useful log body.'


class ReflectionFactory(DjangoModelFactory):
    class Meta:
        model = Reflection

    user = factory.SubFactory(UserFactory)
    event = factory.SubFactory(EventFactory, user=factory.SelfAttribute('..user'))
    title = factory.Sequence(lambda n: f'Reflection {n}')
    clarity_check = 'Clear'
    data = {'prompt': 'What happened?', 'response': 'A useful response.'}
