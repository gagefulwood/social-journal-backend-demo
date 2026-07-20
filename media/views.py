import hashlib
import re
import uuid
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardResultsPagination
from core.permissions import IsOwner

from .filters import MediaAssetFilter
from .models import MediaAsset, MediaUploadSession
from .serializers import (
    MediaAssetListSerializer,
    MediaAssetSerializer,
    MediaUploadSessionSerializer,
)
from .signing import unsign_media_content
from .upload_handlers import CappedMediaUploadHandler
from .services import (
    MediaVerificationError,
    SUPPORTED_AUDIO_MIME_TYPES,
    SUPPORTED_VIDEO_MIME_TYPES,
    asset_reference_counts,
    enabled_mime_types,
    media_capabilities,
    normalize_content_type,
    owner_quota_failure,
    safe_original_filename,
)


RANGE_PATTERN = re.compile(r'^bytes=(\d*)-(\d*)$')
RETRYABLE_SESSION_FAILURE_CODES = frozenset(
    {
        'cancelled',
        'session_expired',
        'upload_cancelled',
        'upload_storage_error',
        'media_probe_timeout',
        'owner_asset_limit_reached',
        'owner_storage_quota_exceeded',
    }
)


class MediaCapabilitiesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(media_capabilities())


class MediaUploadSessionDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MediaUploadSessionSerializer
    http_method_names = ['get', 'delete', 'head', 'options']

    def get_queryset(self):
        return MediaUploadSession.objects.for_user(
            self.request.user
        ).select_related('media_asset')

    def delete(self, request, *args, **kwargs):
        current = self.get_object()
        with transaction.atomic():
            session = MediaUploadSession.objects.for_user(
                request.user
            ).select_for_update().get(pk=current.pk)
            if session.status == MediaUploadSession.STATUS_READY:
                return Response(
                    {
                        'detail': 'A completed upload cannot be cancelled.',
                        'code': 'upload_already_completed',
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            session.status = MediaUploadSession.STATUS_ABORTED
            session.failure_code = 'cancelled'
            session.save(
                update_fields=[
                    'status',
                    'failure_code',
                    'updated_timestamp',
                ]
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MediaUploadCancelView(APIView):
    """Cancel by owner/idempotency key, including races before session creation."""

    permission_classes = [IsAuthenticated]
    http_method_names = ['delete', 'post', 'options']

    def delete(self, request):
        return self._cancel(
            request,
            request.headers.get('Idempotency-Key', ''),
        )

    def post(self, request):
        # POST exists for page-exit beacon delivery, where browsers cannot set
        # the DELETE method or custom Idempotency-Key header reliably.
        return self._cancel(request, request.data.get('idempotency_key', ''))

    def _cancel(self, request, raw_key):
        idempotency_key = str(raw_key).strip()
        if not idempotency_key or len(idempotency_key) > 512:
            return Response(
                {
                    'detail': 'Provide a valid Idempotency-Key to cancel.',
                    'code': 'invalid_idempotency_key',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        key_hash = _idempotency_hash(idempotency_key)
        now = timezone.now()
        with transaction.atomic():
            type(request.user).objects.select_for_update().get(
                pk=request.user.pk,
            )
            session = MediaUploadSession.objects.for_user(
                request.user,
            ).select_for_update().filter(
                idempotency_key_hash=key_hash,
            ).first()
            if session is None:
                MediaUploadSession.objects.create(
                    user=request.user,
                    idempotency_key_hash=key_hash,
                    status=MediaUploadSession.STATUS_ABORTED,
                    failure_code='cancellation_requested',
                    expires_at=now + timedelta(
                        seconds=settings.MEDIA_UPLOAD_SESSION_EXPIRY_SECONDS
                    ),
                )
                return Response(status=status.HTTP_204_NO_CONTENT)

            asset = session.media_asset
            if asset is not None and asset.is_active:
                asset = MediaAsset.objects.select_for_update().get(pk=asset.pk)
                references = asset_reference_counts(asset)
                if references:
                    return Response(
                        {
                            'detail': (
                                'The completed upload is already in use and '
                                'cannot be cancelled.'
                            ),
                            'code': 'upload_already_attached',
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                asset.is_active = False
                asset.deleted_timestamp = now
                asset.save(
                    update_fields=[
                        'is_active',
                        'deleted_timestamp',
                        'updated_timestamp',
                    ]
                )

            session.status = MediaUploadSession.STATUS_ABORTED
            session.failure_code = 'cancellation_requested'
            session.save(
                update_fields=[
                    'status',
                    'failure_code',
                    'updated_timestamp',
                ]
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MediaAssetViewSet(viewsets.ModelViewSet):
    '''
    Owner-scoped media metadata, verified direct uploads, and private content.

    Uploads are synchronous HTTP requests. The upload-session record adds
    owner-scoped idempotency and observable terminal state; it does not imply
    provider multipart, background processing, or cross-device resume.
    '''

    permission_classes = [IsAuthenticated, IsOwner]
    pagination_class = StandardResultsPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MediaAssetFilter
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return MediaAsset.objects.none()
        return MediaAsset.objects.for_user(self.request.user).select_related(
            'media_type',
            'user',
        )

    def get_serializer_class(self):
        if self.action == 'list':
            return MediaAssetListSerializer
        return MediaAssetSerializer

    def create(self, request, *args, **kwargs):
        idempotency_key = request.headers.get('Idempotency-Key', '').strip()
        if len(idempotency_key) > 512:
            return Response(
                {
                    'detail': 'Idempotency-Key must be 512 characters or fewer.',
                    'code': 'invalid_idempotency_key',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        key_hash = _idempotency_hash(
            idempotency_key or f'generated:{uuid.uuid4()}'
        )
        now = timezone.now()
        retried_session = False
        try:
            with transaction.atomic():
                type(request.user).objects.select_for_update().get(
                    pk=request.user.pk
                )
                MediaUploadSession.objects.for_user(request.user).filter(
                    status__in=[
                        MediaUploadSession.STATUS_PENDING,
                        MediaUploadSession.STATUS_VERIFYING,
                    ],
                    expires_at__lte=now,
                ).update(
                    status=MediaUploadSession.STATUS_ABORTED,
                    failure_code='session_expired',
                    updated_timestamp=now,
                )
                existing = MediaUploadSession.objects.for_user(
                    request.user
                ).select_for_update().filter(
                    idempotency_key_hash=key_hash
                ).first()
                if existing and not _session_can_retry(existing):
                    return self._replay_session(existing)

                active_uploads = MediaUploadSession.objects.for_user(
                    request.user
                ).filter(
                    status__in=[
                        MediaUploadSession.STATUS_PENDING,
                        MediaUploadSession.STATUS_VERIFYING,
                    ],
                    expires_at__gt=now,
                ).count()
                maximum_concurrent = settings.MEDIA_MAX_CONCURRENT_UPLOADS
                if (
                    maximum_concurrent
                    and active_uploads >= maximum_concurrent
                ):
                    return Response(
                        {
                            'detail': (
                                'The concurrent upload limit has been reached.'
                            ),
                            'code': 'concurrent_upload_limit_reached',
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )

                session_values = {
                    'original_filename': '',
                    'claimed_content_type': '',
                    'expected_bytes': None,
                    'status': MediaUploadSession.STATUS_PENDING,
                    'failure_code': '',
                    'expires_at': now + timedelta(
                        seconds=settings.MEDIA_UPLOAD_SESSION_EXPIRY_SECONDS
                    ),
                }
                if existing:
                    retried_session = True
                    for field, value in session_values.items():
                        setattr(existing, field, value)
                    existing.media_asset = None
                    existing.save(
                        update_fields=[
                            *session_values.keys(),
                            'media_asset',
                            'updated_timestamp',
                        ]
                    )
                    session = existing
                else:
                    session = MediaUploadSession.objects.create(
                        user=request.user,
                        idempotency_key_hash=key_hash,
                        **session_values,
                    )
        except IntegrityError:
            return self._replay_session(self._session_for_hash(key_hash))

        declared_length = request.headers.get('Content-Length')
        try:
            declared_length = int(declared_length) if declared_length else None
        except (TypeError, ValueError):
            declared_length = None
        maximum_request_bytes = settings.MEDIA_UPLOAD_REQUEST_MAX_BYTES
        if declared_length and declared_length > maximum_request_bytes:
            self._fail_session(session, 'upload_request_too_large')
            return Response(
                {
                    'detail': (
                        'The upload request exceeds the server request limit.'
                    ),
                    'code': 'upload_request_too_large',
                    'upload_session_id': str(session.id),
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                headers={'Upload-Session-Id': str(session.id)},
            )

        raw_request = request._request
        raw_request.upload_handlers.insert(
            0,
            CappedMediaUploadHandler(
                raw_request,
                maximum_bytes=maximum_request_bytes,
            ),
        )
        upload = request.FILES.get('file')
        if getattr(raw_request, '_media_upload_limit_exceeded', False):
            self._fail_session(session, 'upload_request_too_large')
            return Response(
                {
                    'detail': (
                        'The upload request exceeds the server request limit.'
                    ),
                    'code': 'upload_request_too_large',
                    'upload_session_id': str(session.id),
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                headers={'Upload-Session-Id': str(session.id)},
            )

        with transaction.atomic():
            locked_session = MediaUploadSession.objects.select_for_update().get(
                pk=session.pk,
            )
            if locked_session.status == MediaUploadSession.STATUS_ABORTED:
                return Response(
                    {
                        'detail': 'The upload session was cancelled.',
                        'code': 'upload_cancelled',
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            locked_session.original_filename = (
                safe_original_filename(getattr(upload, 'name', ''))
                if upload else ''
            )
            locked_session.claimed_content_type = (
                normalize_content_type(getattr(upload, 'content_type', ''))
                if upload else ''
            )
            locked_session.expected_bytes = getattr(upload, 'size', None)
            locked_session.status = MediaUploadSession.STATUS_VERIFYING
            locked_session.save(
                update_fields=[
                    'original_filename',
                    'claimed_content_type',
                    'expected_bytes',
                    'status',
                    'updated_timestamp',
                ]
            )

        serializer = self.get_serializer(data=request.data)
        created_asset = None
        try:
            serializer.is_valid(raise_exception=True)
            verification = serializer._verified_media
            with transaction.atomic():
                # Serialize quota decisions for one owner so simultaneous
                # requests cannot both pass the same count/byte boundary.
                type(request.user).objects.select_for_update().get(
                    pk=request.user.pk
                )
                locked_session = MediaUploadSession.objects.select_for_update().get(
                    pk=session.pk
                )
                if locked_session.status == MediaUploadSession.STATUS_ABORTED:
                    raise MediaVerificationError(
                        'upload_cancelled',
                        'The upload session was cancelled.',
                    )
                quota_failure = owner_quota_failure(
                    request.user,
                    verification.file_size,
                )
                if quota_failure:
                    raise quota_failure
                created_asset = serializer.save(user=request.user)
                locked_session.media_asset = created_asset
                locked_session.status = MediaUploadSession.STATUS_READY
                locked_session.failure_code = ''
                locked_session.save(
                    update_fields=[
                        'media_asset',
                        'status',
                        'failure_code',
                        'updated_timestamp',
                    ]
                )
        except MediaVerificationError as exc:
            self._fail_session(session, exc.code)
            return Response(
                {'detail': exc.message, 'code': exc.code},
                status=status.HTTP_409_CONFLICT,
            )
        except serializers.ValidationError as exc:
            failure_code = getattr(serializer, 'failure_code', '') or (
                _first_error_code(exc.detail) or 'upload_validation_failed'
            )
            self._fail_session(session, failure_code)
            return Response(
                {
                    'detail': exc.detail,
                    'code': failure_code,
                    'upload_session_id': str(session.id),
                },
                status=status.HTTP_400_BAD_REQUEST,
                headers={'Upload-Session-Id': str(session.id)},
            )
        except Exception:
            if created_asset and created_asset.file:
                created_asset.file.storage.delete(created_asset.file.name)
            self._fail_session(session, 'upload_storage_error')
            return Response(
                {
                    'detail': 'The upload could not be persisted safely.',
                    'code': 'upload_storage_error',
                    'upload_session_id': str(session.id),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={'Upload-Session-Id': str(session.id)},
            )

        output = dict(self.get_serializer(created_asset).data)
        output['upload_session_id'] = str(session.id)
        output['upload_session_status'] = MediaUploadSession.STATUS_READY
        headers = self.get_success_headers(output)
        headers['Upload-Session-Id'] = str(session.id)
        if retried_session:
            headers['Upload-Session-Retried'] = 'true'
        return Response(output, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, *args, **kwargs):
        current = self.get_object()
        with transaction.atomic():
            instance = MediaAsset.objects.for_user(
                request.user
            ).select_for_update().get(pk=current.pk, is_active=True)
            references = asset_reference_counts(instance)
            if references:
                return Response(
                    {
                        'detail': (
                            'Detach this media asset before deleting it.'
                        ),
                        'code': 'media_in_use',
                        'reference_count': sum(references.values()),
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            instance.is_active = False
            instance.deleted_timestamp = timezone.now()
            instance.save(
                update_fields=[
                    'is_active',
                    'deleted_timestamp',
                    'updated_timestamp',
                ]
            )
        # Bytes are retained for the configured recovery window. The idempotent
        # cleanup_media command purges them only after another reference check.
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=['get', 'head'],
        url_path='content',
        authentication_classes=[],
        permission_classes=[AllowAny],
    )
    def content(self, request, pk=None):
        token = request.query_params.get('token', '')
        if not token:
            return Response(
                {
                    'detail': 'A signed media URL is required.',
                    'code': 'signed_media_url_required',
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            owner_id, signed_asset_id = unsign_media_content(token)
        except signing.SignatureExpired:
            return Response(
                {
                    'detail': 'The signed media URL has expired.',
                    'code': 'signed_media_url_expired',
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except (signing.BadSignature, TypeError, ValueError):
            return Response(
                {
                    'detail': 'The signed media URL is invalid.',
                    'code': 'signed_media_url_invalid',
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if str(signed_asset_id) != str(pk):
            return Response(
                {
                    'detail': 'The signed media URL is invalid.',
                    'code': 'signed_media_url_invalid',
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        asset = get_object_or_404(
            MediaAsset.objects.select_related('media_type').filter(
                user_id=owner_id,
                is_active=True,
            ),
            pk=pk,
        )
        if asset.status != MediaAsset.STATUS_READY:
            return Response(
                {
                    'detail': 'The media asset is not ready.',
                    'code': 'media_not_ready',
                    'status': asset.status,
                },
                status=status.HTTP_409_CONFLICT,
            )
        if not asset.file:
            return Response(
                {
                    'detail': 'The media content is unavailable.',
                    'code': 'media_bytes_missing',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        storage = asset.file.storage
        name = asset.file.name
        if not storage.exists(name):
            return Response(
                {
                    'detail': 'The media content is unavailable.',
                    'code': 'media_bytes_missing',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if _is_local_storage(storage, name):
            return _local_content_response(request, asset)
        return _private_storage_redirect(asset)

    def _session_for_hash(self, key_hash):
        return MediaUploadSession.objects.for_user(
            self.request.user
        ).select_related('media_asset', 'media_asset__media_type').filter(
            idempotency_key_hash=key_hash
        ).first()

    def _replay_session(self, session):
        session_data = MediaUploadSessionSerializer(
            session,
            context=self.get_serializer_context(),
        ).data
        headers = {
            'Upload-Session-Id': str(session.id),
            'Idempotency-Replayed': 'true',
        }
        if (
            session.status == MediaUploadSession.STATUS_READY
            and session.media_asset_id
            and session.media_asset.is_active
        ):
            output = dict(self.get_serializer(session.media_asset).data)
            output['upload_session_id'] = str(session.id)
            output['upload_session_status'] = session.status
            return Response(output, status=status.HTTP_200_OK, headers=headers)

        code = {
            MediaUploadSession.STATUS_PENDING: 'upload_in_progress',
            MediaUploadSession.STATUS_VERIFYING: 'upload_in_progress',
            MediaUploadSession.STATUS_FAILED: (
                session.failure_code or 'upload_failed'
            ),
            MediaUploadSession.STATUS_ABORTED: (
                session.failure_code or 'upload_aborted'
            ),
            MediaUploadSession.STATUS_READY: 'upload_result_unavailable',
        }.get(session.status, 'upload_state_conflict')
        return Response(
            {
                'detail': 'This idempotency key already has an upload result.',
                'code': code,
                'upload_session': session_data,
            },
            status=status.HTTP_409_CONFLICT,
            headers=headers,
        )

    @staticmethod
    def _fail_session(session, failure_code):
        MediaUploadSession.objects.filter(pk=session.pk).exclude(
            status=MediaUploadSession.STATUS_ABORTED
        ).update(
            status=MediaUploadSession.STATUS_FAILED,
            failure_code=failure_code,
            updated_timestamp=timezone.now(),
        )


def _local_content_response(request, asset):
    storage = asset.file.storage
    size = storage.size(asset.file.name)
    byte_range = request.headers.get('Range')
    parsed_range = _parse_range(byte_range, size) if byte_range else None
    if byte_range and parsed_range is None:
        response = HttpResponse(status=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        response['Content-Range'] = f'bytes */{size}'
        response['Accept-Ranges'] = 'bytes'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response

    start, end = parsed_range or (0, max(0, size - 1))
    length = end - start + 1 if size else 0
    response_status = (
        status.HTTP_206_PARTIAL_CONTENT
        if parsed_range
        else status.HTTP_200_OK
    )
    content_type, inline = _safe_delivery_content_type(asset)

    if request.method == 'HEAD':
        response = HttpResponse(status=response_status, content_type=content_type)
    else:
        file_handle = storage.open(asset.file.name, 'rb')
        file_handle.seek(start)
        response = StreamingHttpResponse(
            _file_chunks(file_handle, length),
            status=response_status,
            content_type=content_type,
        )
    response['Content-Length'] = str(length)
    response['Accept-Ranges'] = 'bytes'
    if parsed_range:
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
    response['Content-Disposition'] = content_disposition_header(
        not inline,
        asset.original_filename,
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    if asset.checksum:
        response['ETag'] = f'"sha256-{asset.checksum}"'
    return response


def _private_storage_redirect(asset):
    if (
        not settings.AWS_QUERYSTRING_AUTH
        or settings.AWS_QUERYSTRING_EXPIRE
        > settings.MEDIA_NONLOCAL_URL_MAX_EXPIRY_SECONDS
    ):
        return Response(
            {
                'detail': 'Private media delivery is not configured safely.',
                'code': 'private_media_delivery_unavailable',
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    url = asset.file.storage.url(asset.file.name)
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.query:
        return Response(
            {
                'detail': 'The storage backend did not return a signed URL.',
                'code': 'private_media_delivery_unavailable',
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    response = HttpResponse(status=status.HTTP_302_FOUND)
    response['Location'] = url
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _is_local_storage(storage, name):
    try:
        storage.path(name)
    except (AttributeError, NotImplementedError):
        return False
    return True


def _safe_delivery_content_type(asset):
    content_type = normalize_content_type(
        asset.detected_content_type or asset.content_type
    )
    allowed = set(enabled_mime_types()['image'])
    if asset.verification_method == 'ffprobe':
        allowed.update(
            value
            for value in settings.MEDIA_ALLOWED_VIDEO_MIME_TYPES
            if value in SUPPORTED_VIDEO_MIME_TYPES
        )
        allowed.update(
            value
            for value in settings.MEDIA_ALLOWED_AUDIO_MIME_TYPES
            if value in SUPPORTED_AUDIO_MIME_TYPES
        )
    if content_type in allowed:
        return content_type, True
    return 'application/octet-stream', False


def _parse_range(value, size):
    if size <= 0 or ',' in value:
        return None
    match = RANGE_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if not first:
        suffix = int(last)
        if suffix <= 0:
            return None
        return max(0, size - suffix), size - 1
    start = int(first)
    if start >= size:
        return None
    end = int(last) if last else size - 1
    if end < start:
        return None
    return start, min(end, size - 1)


def _file_chunks(file_handle, length):
    remaining = length
    try:
        while remaining > 0:
            chunk = file_handle.read(
                min(settings.MEDIA_CONTENT_CHUNK_SIZE, remaining)
            )
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        file_handle.close()


def _idempotency_hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _session_can_retry(session):
    return (
        session.media_asset_id is None
        and session.status in {
            MediaUploadSession.STATUS_FAILED,
            MediaUploadSession.STATUS_ABORTED,
        }
        and session.failure_code in RETRYABLE_SESSION_FAILURE_CODES
    )


def _first_error_code(detail):
    if isinstance(detail, dict):
        for value in detail.values():
            code = _first_error_code(value)
            if code:
                return code
    elif isinstance(detail, (list, tuple)):
        for value in detail:
            code = _first_error_code(value)
            if code:
                return code
    else:
        return getattr(detail, 'code', None)
    return None
