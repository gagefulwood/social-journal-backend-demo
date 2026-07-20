from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from lookups.models import MediaType
from lookups.serializers import MediaTypeSerializer

from .models import MediaAsset, MediaUploadSession
from .signing import sign_media_content
from .services import (
    MediaVerificationError,
    media_type_for_family,
    safe_original_filename,
    verify_uploaded_file,
)


class MediaContentUrlMixin:
    def get_url(self, obj):
        return self.get_content_url(obj)

    def get_content_url(self, obj):
        path = reverse('media-content', args=[obj.pk])
        path = f'{path}?{urlencode({"token": sign_media_content(obj)})}'
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path


class MediaAssetListSerializer(
    MediaContentUrlMixin,
    serializers.ModelSerializer,
):
    url = serializers.SerializerMethodField()
    content_url = serializers.SerializerMethodField()
    media_type = MediaTypeSerializer(read_only=True)

    class Meta:
        model = MediaAsset
        fields = [
            'id',
            'url',
            'content_url',
            'media_type',
            'original_filename',
            'content_type',
            'detected_content_type',
            'file_size',
            'status',
            'failure_code',
            'width',
            'height',
            'pixel_count',
            'duration_ms',
            'alt_text',
            'caption',
            'created_timestamp',
        ]
        read_only_fields = fields


class MediaAssetSerializer(
    MediaContentUrlMixin,
    serializers.ModelSerializer,
):
    file = serializers.FileField(write_only=True, required=False)
    url = serializers.SerializerMethodField()
    content_url = serializers.SerializerMethodField()
    media_type = MediaTypeSerializer(read_only=True)
    media_type_id = serializers.PrimaryKeyRelatedField(
        queryset=MediaType.objects.all(),
        source='media_type',
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = MediaAsset
        fields = [
            'id',
            'file',
            'url',
            'content_url',
            'media_type',
            'media_type_id',
            'original_filename',
            'claimed_content_type',
            'content_type',
            'detected_content_type',
            'file_size',
            'checksum',
            'status',
            'verification_method',
            'failure_code',
            'width',
            'height',
            'pixel_count',
            'duration_ms',
            'verified_timestamp',
            'alt_text',
            'caption',
            'created_timestamp',
            'updated_timestamp',
            'is_active',
        ]
        read_only_fields = [
            'url',
            'content_url',
            'original_filename',
            'claimed_content_type',
            'content_type',
            'detected_content_type',
            'file_size',
            'checksum',
            'status',
            'verification_method',
            'failure_code',
            'width',
            'height',
            'pixel_count',
            'duration_ms',
            'verified_timestamp',
            'created_timestamp',
            'updated_timestamp',
            'is_active',
        ]

    def validate_file(self, uploaded_file):
        try:
            self._verified_media = verify_uploaded_file(uploaded_file)
        except MediaVerificationError as exc:
            self.failure_code = exc.code
            raise serializers.ValidationError(
                exc.message,
                code=exc.code,
            ) from exc
        return uploaded_file

    def validate(self, attrs):
        if self.instance is None and 'file' not in attrs:
            self.failure_code = 'file_required'
            raise serializers.ValidationError(
                {'file': ErrorDetail(
                    'A media file is required.',
                    code='file_required',
                )}
            )
        if self.instance is not None and 'file' in attrs:
            self.failure_code = 'file_replacement_unsupported'
            raise serializers.ValidationError(
                {'file': ErrorDetail(
                    'Replace media by uploading a new asset.',
                    code='file_replacement_unsupported',
                )}
            )
        if self.instance is not None and 'media_type' in attrs:
            self.failure_code = 'media_type_immutable'
            raise serializers.ValidationError(
                {'media_type_id': ErrorDetail(
                    'Media type is inferred from verified bytes and cannot be changed.',
                    code='media_type_immutable',
                )}
            )
        return attrs

    def create(self, validated_data):
        uploaded_file = validated_data['file']
        verification = self._verified_media
        requested_media_type = validated_data.pop('media_type', None)
        inferred_media_type = media_type_for_family(verification.family)
        if (
            requested_media_type is not None
            and requested_media_type.name.upper() != verification.family.upper()
        ):
            self.failure_code = 'media_type_mismatch'
            raise serializers.ValidationError(
                {'media_type_id': ErrorDetail(
                    'The selected media type does not match the uploaded bytes.',
                    code='media_type_mismatch',
                )}
            )

        validated_data.update(
            original_filename=safe_original_filename(uploaded_file.name),
            claimed_content_type=verification.claimed_content_type,
            content_type=verification.detected_content_type,
            detected_content_type=verification.detected_content_type,
            file_size=verification.file_size,
            checksum=verification.checksum,
            media_type=inferred_media_type,
            status=MediaAsset.STATUS_READY,
            verification_method=verification.verification_method,
            failure_code='',
            width=verification.width,
            height=verification.height,
            pixel_count=verification.pixel_count,
            duration_ms=verification.duration_ms,
            verified_timestamp=timezone.now(),
        )
        instance = MediaAsset(**validated_data)
        try:
            instance.save()
        except Exception:
            # FileField storage is not transactional. If bytes were written in
            # pre_save but the database insert failed, remove that exact key.
            if (
                instance.file
                and instance.file.name
                and getattr(instance.file, '_committed', False)
            ):
                instance.file.storage.delete(instance.file.name)
            raise
        return instance


class MediaUploadSessionSerializer(serializers.ModelSerializer):
    media_asset_id = serializers.IntegerField(read_only=True)
    media_asset_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaUploadSession
        fields = [
            'id',
            'status',
            'failure_code',
            'original_filename',
            'claimed_content_type',
            'expected_bytes',
            'media_asset_id',
            'media_asset_url',
            'expires_at',
            'created_timestamp',
            'updated_timestamp',
        ]
        read_only_fields = fields

    def get_media_asset_url(self, obj):
        if not obj.media_asset_id:
            return None
        path = reverse('media-detail', args=[obj.media_asset_id])
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path
