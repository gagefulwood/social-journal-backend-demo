import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import PurePath

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from PIL import Image, UnidentifiedImageError

from lookups.models import MediaType

from .models import MediaAsset


SUPPORTED_IMAGE_MIME_TYPES = frozenset(
    {'image/jpeg', 'image/png', 'image/webp'}
)
SUPPORTED_VIDEO_MIME_TYPES = frozenset(
    {'video/mp4', 'video/quicktime', 'video/webm'}
)
SUPPORTED_AUDIO_MIME_TYPES = frozenset(
    {'audio/mpeg', 'audio/mp4', 'audio/aac', 'audio/ogg', 'audio/wav'}
)

CONTENT_TYPE_ALIASES = {
    'audio/mp3': 'audio/mpeg',
    'audio/x-m4a': 'audio/mp4',
    'audio/m4a': 'audio/mp4',
    'audio/x-wav': 'audio/wav',
    'audio/wave': 'audio/wav',
    'image/jpg': 'image/jpeg',
    'video/x-m4v': 'video/mp4',
}

IMAGE_FORMAT_MIME_TYPES = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'WEBP': 'image/webp',
}


class MediaVerificationError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VerifiedMedia:
    family: str
    detected_content_type: str
    claimed_content_type: str
    file_size: int
    checksum: str
    verification_method: str
    width: int | None = None
    height: int | None = None
    pixel_count: int | None = None
    duration_ms: int | None = None


def enabled_mime_types():
    av_probe_enabled = ffprobe_available()
    return {
        'image': tuple(
            value
            for value in settings.MEDIA_ALLOWED_IMAGE_MIME_TYPES
            if value in SUPPORTED_IMAGE_MIME_TYPES
        ),
        'video': tuple(
            value
            for value in settings.MEDIA_ALLOWED_VIDEO_MIME_TYPES
            if av_probe_enabled and value in SUPPORTED_VIDEO_MIME_TYPES
        ),
        'audio': tuple(
            value
            for value in settings.MEDIA_ALLOWED_AUDIO_MIME_TYPES
            if av_probe_enabled and value in SUPPORTED_AUDIO_MIME_TYPES
        ),
    }


def media_capabilities():
    mime_types = enabled_mime_types()
    owner_max_assets = settings.MEDIA_OWNER_MAX_ASSETS
    has_ffprobe = ffprobe_available()
    return {
        'upload': {
            'strategy': 'direct_api',
            'endpoint': '/api/media/',
            'multipart_field': 'file',
            'files_per_request': 1,
            'idempotency_header': 'Idempotency-Key',
            'idempotency_supported': True,
            'http_progress_supported': True,
            'request_cancellation_supported': True,
            'cancel_endpoint': '/api/media/uploads/cancel/',
            'cancel_idempotency_header': 'Idempotency-Key',
            'cancel_beacon_supported': True,
            'resumable_upload_supported': False,
            'provider_multipart_supported': False,
        },
        'mime_types': mime_types,
        'limits': {
            'image_max_bytes': settings.MEDIA_IMAGE_MAX_BYTES,
            'video_max_bytes': settings.MEDIA_VIDEO_MAX_BYTES,
            'audio_max_bytes': settings.MEDIA_AUDIO_MAX_BYTES,
            'video_max_duration_seconds': (
                settings.MEDIA_VIDEO_MAX_DURATION_SECONDS
            ),
            'video_max_width': settings.MEDIA_VIDEO_MAX_WIDTH,
            'video_max_height': settings.MEDIA_VIDEO_MAX_HEIGHT,
            'audio_max_duration_seconds': (
                settings.MEDIA_AUDIO_MAX_DURATION_SECONDS
            ),
            'image_max_pixels': settings.MEDIA_IMAGE_MAX_PIXELS,
            'image_max_edge': settings.MEDIA_IMAGE_MAX_EDGE,
            'chapter_max_assets': settings.MEDIA_CHAPTER_MAX_ASSETS,
            'event_max_assets': settings.MEDIA_EVENT_MAX_ASSETS,
            'chapter_original_bytes_max': (
                settings.MEDIA_CHAPTER_ORIGINAL_BYTES_MAX
            ),
            'event_original_bytes_max': settings.MEDIA_EVENT_ORIGINAL_BYTES_MAX,
            'owner_storage_quota_bytes': (
                settings.MEDIA_OWNER_STORAGE_QUOTA_BYTES
            ),
            'owner_max_assets': owner_max_assets or None,
            'concurrent_uploads': settings.MEDIA_MAX_CONCURRENT_UPLOADS,
            'upload_session_expiry_seconds': (
                settings.MEDIA_UPLOAD_SESSION_EXPIRY_SECONDS
            ),
        },
        'verification': {
            'actual_bytes_verified': True,
            'checksum': 'sha256',
            'image_full_decode': True,
            'container_signature_validation': True,
            'duration_probe': has_ffprobe,
            'ffprobe': has_ffprobe,
            'mime_library': False,
        },
        'processing': {
            'asynchronous_worker': False,
            'transcoding': False,
            'variants': False,
            'posters': False,
            'metadata_stripping': False,
        },
        'delivery': {
            'authenticated_content_endpoint': True,
            'signed_content_urls': True,
            'signed_url_expiry_seconds': (
                settings.MEDIA_CONTENT_URL_EXPIRY_SECONDS
            ),
            'range_requests': True,
            'head_requests': True,
            'nonlocal_private_redirect': True,
            'public_storage_paths': False,
        },
    }


def normalize_content_type(value):
    normalized = (value or '').split(';', 1)[0].strip().lower()
    return CONTENT_TYPE_ALIASES.get(normalized, normalized)


def safe_original_filename(value):
    # PurePath on POSIX does not treat a backslash as a separator, so normalize
    # both browser path conventions before taking the basename.
    normalized = (value or '').replace('\\', '/')
    filename = PurePath(normalized).name
    filename = ''.join(character for character in filename if ord(character) >= 32)
    return filename[:255] or 'upload'


def verify_uploaded_file(uploaded_file):
    file_size = int(getattr(uploaded_file, 'size', 0) or 0)
    if file_size <= 0:
        raise MediaVerificationError('empty_file', 'The uploaded file is empty.')

    claimed_content_type = normalize_content_type(
        getattr(uploaded_file, 'content_type', '')
    )
    probe = _read_probe(uploaded_file, file_size)

    if _looks_like_image(probe):
        _enforce_family_byte_limit('image', file_size)
        detected, width, height = _verify_image(uploaded_file)
        family = 'image'
        verification_method = 'pillow_decode'
        duration_ms = None
    else:
        detected = _detect_container_content_type(probe, file_size)
        family = detected.split('/', 1)[0]
        _enforce_family_byte_limit(family, file_size)
        width, height, duration_ms = _probe_av_media(
            uploaded_file,
            family=family,
        )
        verification_method = 'ffprobe'

    configured = enabled_mime_types()[family]
    if detected not in configured:
        raise MediaVerificationError(
            'unsupported_media_type',
            f'{detected} uploads are not enabled.',
        )

    if claimed_content_type and claimed_content_type != 'application/octet-stream':
        if claimed_content_type != detected:
            raise MediaVerificationError(
                'content_type_mismatch',
                'The declared content type does not match the uploaded bytes.',
            )

    checksum = _sha256(uploaded_file)
    return VerifiedMedia(
        family=family,
        detected_content_type=detected,
        claimed_content_type=claimed_content_type,
        file_size=file_size,
        checksum=checksum,
        verification_method=verification_method,
        width=width,
        height=height,
        pixel_count=width * height if width and height else None,
        duration_ms=duration_ms,
    )


def ffprobe_available():
    return shutil.which(settings.MEDIA_FFPROBE_BINARY) is not None


def _enforce_family_byte_limit(family, file_size):
    maximum = {
        'image': settings.MEDIA_IMAGE_MAX_BYTES,
        'video': settings.MEDIA_VIDEO_MAX_BYTES,
        'audio': settings.MEDIA_AUDIO_MAX_BYTES,
    }[family]
    if file_size > maximum:
        raise MediaVerificationError(
            f'{family}_too_large',
            f'The uploaded {family} exceeds the {maximum}-byte limit.',
        )


def _probe_av_media(uploaded_file, *, family):
    if not ffprobe_available():
        raise MediaVerificationError(
            'media_probe_unavailable',
            'Audio and video uploads are disabled until ffprobe is available.',
        )

    temporary_path = None
    try:
        path_getter = getattr(uploaded_file, 'temporary_file_path', None)
        if callable(path_getter):
            probe_path = path_getter()
        else:
            uploaded_file.seek(0)
            with tempfile.NamedTemporaryFile(delete=False) as temporary:
                temporary_path = temporary.name
                for chunk in iter(
                    lambda: uploaded_file.read(1024 * 1024),
                    b'',
                ):
                    temporary.write(chunk)
            probe_path = temporary_path

        result = subprocess.run(
            [
                settings.MEDIA_FFPROBE_BINARY,
                '-v',
                'error',
                '-show_entries',
                (
                    'format=duration,format_name:'
                    'stream=codec_type,codec_name,width,height,duration'
                ),
                '-of',
                'json',
                probe_path,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.MEDIA_FFPROBE_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise MediaVerificationError(
                'invalid_media_stream',
                'The media streams could not be decoded safely.',
            )
        try:
            payload = json.loads(result.stdout)
        except (TypeError, ValueError):
            raise MediaVerificationError(
                'invalid_media_stream',
                'The media probe returned an invalid result.',
            ) from None
        return _validate_ffprobe_payload(payload, family=family)
    except subprocess.TimeoutExpired:
        raise MediaVerificationError(
            'media_probe_timeout',
            'The media stream probe timed out.',
        ) from None
    finally:
        uploaded_file.seek(0)
        if temporary_path:
            try:
                import os
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def _validate_ffprobe_payload(payload, *, family):
    if not isinstance(payload, dict):
        raise MediaVerificationError(
            'invalid_media_stream',
            'The media probe returned an invalid result.',
        )
    streams = payload.get('streams')
    if not isinstance(streams, list):
        streams = []
    video_streams = [
        stream for stream in streams if stream.get('codec_type') == 'video'
    ]
    audio_streams = [
        stream for stream in streams if stream.get('codec_type') == 'audio'
    ]
    if family == 'video' and not video_streams:
        raise MediaVerificationError(
            'video_stream_missing',
            'The video container does not contain a video stream.',
        )
    if family == 'audio' and (not audio_streams or video_streams):
        raise MediaVerificationError(
            'audio_stream_invalid',
            'The audio container must contain audio without a video stream.',
        )

    unsupported_video = sorted({
        str(stream.get('codec_name') or '').lower()
        for stream in video_streams
        if str(stream.get('codec_name') or '').lower()
        not in settings.MEDIA_ALLOWED_VIDEO_CODECS
    })
    unsupported_audio = sorted({
        str(stream.get('codec_name') or '').lower()
        for stream in audio_streams
        if str(stream.get('codec_name') or '').lower()
        not in settings.MEDIA_ALLOWED_AUDIO_CODECS
    })
    if unsupported_video or unsupported_audio:
        raise MediaVerificationError(
            'unsupported_media_codec',
            'The media contains an unsupported audio or video codec.',
        )

    width = height = None
    if family == 'video':
        dimensions = []
        for stream in video_streams:
            try:
                stream_width = int(stream.get('width') or 0)
                stream_height = int(stream.get('height') or 0)
            except (TypeError, ValueError):
                stream_width = stream_height = 0
            if stream_width <= 0 or stream_height <= 0:
                raise MediaVerificationError(
                    'video_dimensions_missing',
                    'The video dimensions could not be verified.',
                )
            if (
                stream_width > settings.MEDIA_VIDEO_MAX_WIDTH
                or stream_height > settings.MEDIA_VIDEO_MAX_HEIGHT
            ):
                raise MediaVerificationError(
                    'video_dimensions_too_large',
                    'The video dimensions exceed the configured limit.',
                )
            dimensions.append((stream_width, stream_height))
        width, height = max(dimensions, key=lambda value: value[0] * value[1])

    format_payload = payload.get('format')
    if not isinstance(format_payload, dict):
        format_payload = {}
    duration_candidates = [
        format_payload.get('duration'),
        *(stream.get('duration') for stream in streams),
    ]
    durations = []
    for candidate in duration_candidates:
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            durations.append(value)
    if not durations:
        raise MediaVerificationError(
            'media_duration_missing',
            'The media duration could not be verified.',
        )
    duration = max(durations)
    maximum_duration = (
        settings.MEDIA_VIDEO_MAX_DURATION_SECONDS
        if family == 'video'
        else settings.MEDIA_AUDIO_MAX_DURATION_SECONDS
    )
    if duration > maximum_duration:
        raise MediaVerificationError(
            f'{family}_duration_too_long',
            f'The uploaded {family} exceeds the duration limit.',
        )
    return width, height, round(duration * 1000)


def media_type_for_family(family):
    return MediaType.objects.filter(name=family.upper()).first()


def owner_quota_failure(user, incoming_bytes):
    active_assets = MediaAsset.objects.filter(user=user, is_active=True)
    maximum_assets = settings.MEDIA_OWNER_MAX_ASSETS
    if maximum_assets and active_assets.count() >= maximum_assets:
        return MediaVerificationError(
            'owner_asset_limit_reached',
            'The account media-asset limit has been reached.',
        )

    # Recoverable deletion retains originals for a bounded window. Those bytes
    # continue consuming quota until cleanup physically removes the file key.
    retained_assets = MediaAsset.objects.filter(user=user).exclude(file='')
    used_bytes = retained_assets.aggregate(total=Sum('file_size'))['total'] or 0
    if used_bytes + incoming_bytes > settings.MEDIA_OWNER_STORAGE_QUOTA_BYTES:
        return MediaVerificationError(
            'owner_storage_quota_exceeded',
            'The upload would exceed the account storage quota.',
        )
    return None


def asset_reference_counts(asset):
    counts = {}
    for relation in asset._meta.related_objects:
        accessor = relation.get_accessor_name()
        if not accessor or accessor == 'upload_session':
            continue
        try:
            related = getattr(asset, accessor)
        except relation.related_model.DoesNotExist:
            continue
        if hasattr(related, 'count'):
            count = related.count()
        else:
            count = 1 if related is not None else 0
        if count:
            counts[accessor] = count
    return counts


def asset_is_referenced(asset):
    return bool(asset_reference_counts(asset))


def delete_asset_bytes(asset):
    '''Delete bytes only after rechecking that no domain record references them.'''
    with transaction.atomic():
        current = MediaAsset.objects.select_for_update().get(pk=asset.pk)
        if current.is_active or asset_is_referenced(current) or not current.file:
            return False
        storage = current.file.storage
        name = current.file.name
        if storage.exists(name):
            storage.delete(name)
        current.file = ''
        current.save(update_fields=['file', 'updated_timestamp'])
    return True


def _looks_like_image(probe):
    return (
        probe.startswith(b'\xff\xd8\xff')
        or probe.startswith(b'\x89PNG\r\n\x1a\n')
        or (
            probe.startswith(b'RIFF')
            and len(probe) >= 12
            and probe[8:12] == b'WEBP'
        )
    )


def _verify_image(uploaded_file):
    try:
        uploaded_file.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(uploaded_file) as image:
                detected = IMAGE_FORMAT_MIME_TYPES.get(image.format)
                if not detected:
                    raise MediaVerificationError(
                        'unsupported_media_type',
                        'The image format is not supported.',
                    )
                if getattr(image, 'is_animated', False):
                    raise MediaVerificationError(
                        'animated_image_unsupported',
                        'Animated images are not supported.',
                    )
                image.verify()

            _reject_trailing_image_data(
                uploaded_file,
                detected,
                int(getattr(uploaded_file, 'size', 0) or 0),
            )

            # verify() checks structure but does not decode pixels. Reopen and
            # load once so truncated/corrupt payloads cannot become ready.
            uploaded_file.seek(0)
            with Image.open(uploaded_file) as decoded:
                width, height = _exif_normalized_size(decoded)
                if max(width, height) > settings.MEDIA_IMAGE_MAX_EDGE:
                    raise MediaVerificationError(
                        'image_edge_too_large',
                        'The image dimensions exceed the configured edge limit.',
                    )
                if width * height > settings.MEDIA_IMAGE_MAX_PIXELS:
                    raise MediaVerificationError(
                        'image_pixel_limit_exceeded',
                        'The image exceeds the configured pixel limit.',
                    )
                decoded.load()
        return detected, width, height
    except MediaVerificationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise MediaVerificationError(
            'invalid_image',
            'The image could not be decoded safely.',
        ) from exc
    finally:
        uploaded_file.seek(0)


def _reject_trailing_image_data(uploaded_file, detected, file_size):
    '''Reject payloads Pillow accepts after a complete supported image.'''
    if detected == 'image/jpeg':
        if file_size < 2:
            raise MediaVerificationError('invalid_image', 'Invalid JPEG data.')
        uploaded_file.seek(file_size - 2)
        if uploaded_file.read(2) != b'\xff\xd9':
            raise MediaVerificationError(
                'image_trailing_data',
                'JPEG data must end at its final image marker.',
            )
        return

    if detected == 'image/webp':
        uploaded_file.seek(0)
        header = uploaded_file.read(12)
        declared_size = int.from_bytes(header[4:8], 'little') + 8
        if declared_size != file_size:
            raise MediaVerificationError(
                'image_trailing_data',
                'WebP data contains bytes outside its RIFF container.',
            )
        return

    if detected == 'image/png':
        uploaded_file.seek(8)
        while uploaded_file.tell() < file_size:
            header = uploaded_file.read(8)
            if len(header) != 8:
                break
            chunk_size = int.from_bytes(header[:4], 'big')
            chunk_type = header[4:8]
            chunk_end = uploaded_file.tell() + chunk_size + 4
            if chunk_end > file_size:
                break
            uploaded_file.seek(chunk_size + 4, 1)
            if chunk_type == b'IEND':
                if chunk_size == 0 and uploaded_file.tell() == file_size:
                    return
                break
        raise MediaVerificationError(
            'image_trailing_data',
            'PNG data must end at its IEND chunk.',
        )


def _exif_normalized_size(image):
    """Return dimensions in the orientation browsers use for presentation."""

    width, height = image.size
    orientation = image.getexif().get(274, 1)
    if orientation in {5, 6, 7, 8}:
        return height, width
    return width, height


def _detect_container_content_type(probe, file_size):
    head = probe[:64]
    if len(head) >= 12 and head[4:8] == b'ftyp':
        ftyp_size = int.from_bytes(head[:4], 'big')
        if (
            ftyp_size < 12
            or ftyp_size > file_size
            or b'moov' not in probe
            or b'mdat' not in probe
        ):
            raise MediaVerificationError(
                'invalid_media_container',
                'The ISO media container is incomplete.',
            )
        brand = head[8:12]
        handlers = _isobmff_handlers(probe)
        if brand == b'qt  ':
            return 'video/quicktime'
        if b'vide' in handlers:
            return 'video/mp4'
        if b'soun' in handlers and b'vide' not in handlers:
            return 'audio/mp4'
        if brand.upper() in {b'M4A ', b'M4B ', b'M4P ', b'F4A '}:
            return 'audio/mp4'
        return 'video/mp4'

    if head.startswith(b'\x1aE\xdf\xa3'):
        if (
            b'webm' in probe[:4096].lower()
            and b'\x16\x54\xae\x6b' in probe
        ):
            return 'video/webm'
        raise MediaVerificationError(
            'invalid_media_container',
            'The WebM container is incomplete.',
        )

    if head.startswith(b'OggS'):
        if _valid_ogg_first_page(probe) and any(
            marker in probe[:65536]
            for marker in (b'OpusHead', b'\x01vorbis', b'fLaC')
        ):
            return 'audio/ogg'
        raise MediaVerificationError(
            'unsupported_ogg_codec',
            'The Ogg container does not contain a supported audio signature.',
        )

    if len(head) >= 12 and head[:4] == b'RIFF' and head[8:12] == b'WAVE':
        declared_size = int.from_bytes(head[4:8], 'little') + 8
        if (
            declared_size == file_size
            and b'fmt ' in probe
            and b'data' in probe
        ):
            return 'audio/wav'
        raise MediaVerificationError(
            'invalid_media_container',
            'The WAV container is incomplete or has trailing data.',
        )

    if _looks_like_mp3(probe):
        return 'audio/mpeg'

    if _looks_like_aac_adts(head, file_size):
        return 'audio/aac'

    raise MediaVerificationError(
        'unsupported_media_type',
        'The uploaded bytes do not match a supported media container.',
    )


def _isobmff_handlers(probe):
    handlers = set()
    position = 0
    while True:
        position = probe.find(b'hdlr', position)
        if position < 0:
            return handlers
        handler = probe[position + 12:position + 16]
        if handler in {b'vide', b'soun'}:
            handlers.add(handler)
        position += 4


def _looks_like_mp3_frame(data):
    for position in range(max(0, len(data) - 4)):
        first, second = data[position], data[position + 1]
        if first != 0xFF or second & 0xE0 != 0xE0:
            continue
        version = (second >> 3) & 0x03
        layer = (second >> 1) & 0x03
        if version != 0x01 and layer != 0x00:
            return True
    return False


def _looks_like_mp3(data):
    if data.startswith(b'ID3'):
        if len(data) < 10 or any(byte & 0x80 for byte in data[6:10]):
            return False
        tag_size = (
            (data[6] << 21)
            | (data[7] << 14)
            | (data[8] << 7)
            | data[9]
        )
        start = min(len(data), 10 + tag_size)
        return _looks_like_mp3_frame(data[start:start + 4096])
    return _looks_like_mp3_frame(data[:4096])


def _looks_like_aac_adts(data, file_size):
    if len(data) < 7 or data[0] != 0xFF or data[1] & 0xF6 != 0xF0:
        return False
    frame_length = ((data[3] & 0x03) << 11) | (data[4] << 3) | (data[5] >> 5)
    return 7 <= frame_length <= file_size


def _valid_ogg_first_page(data):
    if len(data) < 27 or data[:4] != b'OggS' or data[4] != 0:
        return False
    segment_count = data[26]
    if len(data) < 27 + segment_count:
        return False
    body_size = sum(data[27:27 + segment_count])
    return len(data) >= 27 + segment_count + body_size


def _read_probe(uploaded_file, file_size):
    maximum = max(1024, settings.MEDIA_CONTAINER_PROBE_BYTES)
    uploaded_file.seek(0)
    if file_size <= maximum:
        probe = uploaded_file.read(maximum)
    else:
        half = maximum // 2
        first = uploaded_file.read(half)
        uploaded_file.seek(max(0, file_size - half))
        last = uploaded_file.read(half)
        probe = first + last
    uploaded_file.seek(0)
    return probe


def _sha256(uploaded_file):
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in iter(lambda: uploaded_file.read(1024 * 1024), b''):
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()
