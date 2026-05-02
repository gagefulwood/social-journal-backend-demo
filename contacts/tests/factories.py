import factory
from factory.django import DjangoModelFactory

from contacts.models import Contact
from users.models import Users


class UserFactory(DjangoModelFactory):
    class Meta:
        model = Users
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.Sequence(lambda n: f"user{n}")
    first_name = "Test"
    last_name = "User"
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        raw_password = extracted or "password123"
        self.set_password(raw_password)
        if create:
            self.save()


class ContactFactory(DjangoModelFactory):
    class Meta:
        model = Contact

    user = factory.SubFactory(UserFactory)
    first_name = factory.Sequence(lambda n: f"Contact{n}")
    last_name = "Person"
    email = factory.Sequence(lambda n: f"contact{n}@example.com")
    phone_number = ""
    is_active = True
