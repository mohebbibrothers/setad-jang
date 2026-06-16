"""
Serializers اپ audit_logs.

این ماژول serializerهای مربوط به نمایش audit log را تعریف می‌کند.

اصول طراحی:
- audit logs فقط خواندنی هستند — هیچ input serializer لازم نیست.
- user به‌صورت inline نمایش داده می‌شود تا query اضافی لازم نباشد.
- فیلدهای JSON (changes, extra_data) به‌صورت خام نمایش داده می‌شوند.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import AuditLog


class AuditLogUserInlineSerializer(serializers.Serializer):
    """نمایش خلاصه کاربر در audit log — بدون اطلاعات حساس."""

    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class AuditLogListSerializer(serializers.ModelSerializer):
    """نمایش خلاصه audit log در لیست — بدون changes و extra_data."""

    user = AuditLogUserInlineSerializer(read_only=True, allow_null=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "user",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "request_id",
            "method",
            "path",
            "created_at",
        )
        read_only_fields = fields


class AuditLogDetailSerializer(serializers.ModelSerializer):
    """نمایش کامل audit log شامل changes و extra_data."""

    user = AuditLogUserInlineSerializer(read_only=True, allow_null=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "user",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "request_id",
            "user_agent",
            "path",
            "method",
            "changes",
            "extra_data",
            "previous_hash",
            "event_hash",
            "hash_version",
            "created_at",
        )
        read_only_fields = fields


class AuditLogExportQuerySerializer(serializers.Serializer):
    """Validation for admin forensic export query parameters."""

    action = serializers.CharField(required=False, allow_blank=True)
    user_id = serializers.IntegerField(required=False, min_value=1)
    resource_type = serializers.CharField(required=False, allow_blank=True)
    resource_id = serializers.CharField(required=False, allow_blank=True)
    request_id = serializers.CharField(required=False, allow_blank=True)
    ip_address = serializers.IPAddressField(required=False)
    method = serializers.CharField(required=False, allow_blank=True)
    path = serializers.CharField(required=False, allow_blank=True)
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        created_after = attrs.get("created_after")
        created_before = attrs.get("created_before")
        if created_after and created_before and created_after > created_before:
            raise serializers.ValidationError(
                {"created_after": "created_after نمی‌تواند بعد از created_before باشد."},
            )
        return attrs


class AuditExportManifestSerializer(serializers.Serializer):
    """OpenAPI schema for the forensic package manifest."""

    schema_version = serializers.CharField()
    generated_at = serializers.DateTimeField()
    record_count = serializers.IntegerField()
    filters = serializers.JSONField()
    chain_verification = serializers.JSONField()
    retention_policy = serializers.JSONField()
    files = serializers.JSONField()
    integrity_note = serializers.CharField()
