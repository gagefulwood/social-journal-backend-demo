import hashlib
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image

from media.services import MediaVerificationError, verify_uploaded_file

from .helpers import image_bytes, image_upload, mp4_bytes, wav_bytes


class MediaVerificationTests(SimpleTestCase):
    def test_png_is_fully_decoded_and_hashed(self):
        payload = image_bytes()

        verified = verify_uploaded_file(image_upload())

        self.assertEqual(verified.family, "image")
        self.assertEqual(verified.detected_content_type, "image/png")
        self.assertEqual((verified.width, verified.height), (4, 3))
        self.assertEqual(verified.checksum, hashlib.sha256(payload).hexdigest())

    def test_jpeg_dimensions_follow_exif_presentation_orientation(self):
        output = BytesIO()
        image = Image.new('RGB', (8, 4), color='navy')
        exif = image.getexif()
        exif[274] = 6
        image.save(output, format='JPEG', exif=exif)
        payload = output.getvalue()

        verified = verify_uploaded_file(
            SimpleUploadedFile(
                'rotated.jpg',
                payload,
                content_type='image/jpeg',
            )
        )

        self.assertEqual((verified.width, verified.height), (4, 8))

    @patch('media.services.ffprobe_available', return_value=True)
    @patch(
        'media.services._probe_av_media',
        return_value=(None, None, 1250),
    )
    def test_validates_wav_structure_with_stream_probe(
        self,
        _probe,
        _available,
    ):
        payload = wav_bytes()
        upload = SimpleUploadedFile(
            "note.wav",
            payload,
            content_type="audio/wav",
        )

        verified = verify_uploaded_file(upload)

        self.assertEqual(verified.detected_content_type, "audio/wav")
        self.assertEqual(verified.verification_method, "ffprobe")
        self.assertEqual(verified.duration_ms, 1250)

    @patch('media.services.ffprobe_available', return_value=True)
    @patch('media.services._probe_av_media')
    def test_distinguishes_mp4_video_and_audio_handlers(
        self,
        probe,
        _available,
    ):
        probe.side_effect = lambda _upload, *, family: (
            (1920, 1080, 2000)
            if family == 'video'
            else (None, None, 2000)
        )
        video = verify_uploaded_file(
            SimpleUploadedFile(
                "clip.mp4",
                mp4_bytes(b"vide"),
                content_type="video/mp4",
            )
        )
        audio = verify_uploaded_file(
            SimpleUploadedFile(
                "recording.m4a",
                mp4_bytes(b"soun"),
                content_type="audio/mp4",
            )
        )

        self.assertEqual(video.detected_content_type, "video/mp4")
        self.assertEqual(audio.detected_content_type, "audio/mp4")

    @patch('media.services.ffprobe_available', return_value=False)
    def test_marker_only_video_is_not_ready_without_real_probe(self, _available):
        upload = SimpleUploadedFile(
            'clip.mp4',
            mp4_bytes(b'vide'),
            content_type='video/mp4',
        )

        with self.assertRaises(MediaVerificationError) as raised:
            verify_uploaded_file(upload)

        self.assertEqual(raised.exception.code, 'media_probe_unavailable')

    def test_rejects_container_signature_without_required_structure(self):
        upload = SimpleUploadedFile(
            "clip.mp4",
            b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42",
            content_type="video/mp4",
        )

        with self.assertRaises(MediaVerificationError) as raised:
            verify_uploaded_file(upload)

        self.assertEqual(raised.exception.code, "invalid_media_container")

    def test_rejects_png_with_trailing_payload(self):
        with self.assertRaises(MediaVerificationError) as raised:
            verify_uploaded_file(image_upload(trailing=b"trailing-data"))

        self.assertEqual(raised.exception.code, "image_trailing_data")

    @override_settings(MEDIA_IMAGE_MAX_BYTES=4)
    def test_enforces_configured_family_byte_limit(self):
        with self.assertRaises(MediaVerificationError) as raised:
            verify_uploaded_file(image_upload())

        self.assertEqual(raised.exception.code, "image_too_large")
