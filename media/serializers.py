from rest_framework import serializers

from lookups.models import MediaType
from lookups.serializers import MediaTypeSerializer

from .models import MediaAsset


class MediaAssetListSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    media_type = MediaTypeSerializer(read_only=True)

    class Meta:
        model = MediaAsset
        fields = [
            'id',
            'url',
            'media_type',
            'original_filename',
            'content_type',
            'file_size',
            'alt_text',
            'caption',
            'created_timestamp',
        ]
        read_only_fields = fields

    def get_url(self, obj):
        if not obj.file:
            return ''
        return obj.file.url


class MediaAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
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
            'media_type',
            'media_type_id',
            'original_filename',
            'content_type',
            'file_size',
            'checksum',
            'alt_text',
            'caption',
            'created_timestamp',
            'updated_timestamp',
            'is_active',
        ]
        read_only_fields = [
            'url',
            'original_filename',
            'content_type',
            'file_size',
            'created_timestamp',
            'updated_timestamp',
            'is_active',
        ]

    def get_url(self, obj):
        if not obj.file:
            return ''
        return obj.file.url

    def create(self, validated_data):
        uploaded_file = validated_data['file']
        validated_data['original_filename'] = uploaded_file.name
        validated_data['content_type'] = getattr(
            uploaded_file,
            'content_type',
            'application/octet-stream',
        )
        validated_data['file_size'] = uploaded_file.size
        validated_data.setdefault(
            'media_type',
            self._media_type_for_content_type(validated_data['content_type']),
        )
        return super().create(validated_data)

    def _media_type_for_content_type(self, content_type):
        prefix = content_type.split('/', 1)[0].upper()
        media_type_name = {
            'IMAGE': 'IMAGE',
            'VIDEO': 'VIDEO',
            'AUDIO': 'AUDIO',
        }.get(prefix, 'DOCUMENT')
        return MediaType.objects.filter(name=media_type_name).first()
