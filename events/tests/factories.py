import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from contacts.tests.factories import ContactFactory, UserFactory
from events.models import Event, EventParticipant


class EventFactory(DjangoModelFactory):
    class Meta:
        model = Event

    user = factory.SubFactory(UserFactory)
    title = factory.Sequence(lambda n: f"Event {n}")
    event_timestamp = factory.LazyFunction(timezone.now)
    description = ""
    end_timestamp = None
    location_label = ""
    tier = "routine"
    impact = ""
    context_category = None
    interaction_mode = None
    mood = None


class EventParticipantFactory(DjangoModelFactory):
    class Meta:
        model = EventParticipant

    event = factory.SubFactory(EventFactory)
    contact = factory.SubFactory(ContactFactory)
