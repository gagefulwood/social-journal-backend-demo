from django.conf import settings
from django.core import signing


CONTENT_URL_SALT = 'social-journal.media-content.v1'


def sign_media_content(asset):
    value = f'{asset.user_id}:{asset.pk}'
    return signing.TimestampSigner(salt=CONTENT_URL_SALT).sign(value)


def unsign_media_content(token):
    value = signing.TimestampSigner(salt=CONTENT_URL_SALT).unsign(
        token,
        max_age=settings.MEDIA_CONTENT_URL_EXPIRY_SECONDS,
    )
    owner_id, asset_id = value.split(':', 1)
    return int(owner_id), int(asset_id)
