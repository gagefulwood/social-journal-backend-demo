from io import BytesIO
import wave

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def image_bytes(image_format='PNG', trailing=b''):
    output = BytesIO()
    Image.new('RGB', (4, 3), color=(113, 84, 200)).save(
        output,
        format=image_format,
    )
    return output.getvalue() + trailing


def image_upload(
    name='avatar.png',
    image_format='PNG',
    content_type='image/png',
    trailing=b'',
):
    return SimpleUploadedFile(
        name,
        image_bytes(image_format, trailing=trailing),
        content_type=content_type,
    )


def wav_bytes():
    output = BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b'\x00\x00' * 16)
    return output.getvalue()


def mp4_bytes(handler=b'vide'):
    def box(kind, payload):
        return (8 + len(payload)).to_bytes(4, 'big') + kind + payload

    ftyp = box(b'ftyp', b'isom\x00\x00\x00\x00isommp42')
    hdlr = box(
        b'hdlr',
        b'\x00\x00\x00\x00'
        + b'\x00\x00\x00\x00'
        + handler
        + b'\x00' * 12
        + b'Test\x00',
    )
    moov = box(b'moov', box(b'trak', box(b'mdia', hdlr)))
    mdat = box(b'mdat', b'\x00' * 16)
    return ftyp + moov + mdat
