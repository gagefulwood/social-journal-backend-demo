import factory
from factory.django import DjangoModelFactory

from contacts.tests.factories import UserFactory
from media.models import MediaAsset
from lookups.models import MediaType


def default_image_type():
    media_type = MediaType.objects.filter(name='IMAGE').first()
    if media_type:
        return media_type
    return MediaType.objects.create(name='IMAGE', is_system_default=True)


class MediaAssetFactory(DjangoModelFactory):
    class Meta:
        model = MediaAsset

    user = factory.SubFactory(UserFactory)
    file = 'media/test.png'
    media_type = factory.LazyFunction(default_image_type)
    original_filename = factory.Sequence(lambda n: f'image-{n}.png')
    content_type = 'image/png'
    file_size = 10
    is_active = True
