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
            "changes",
            "extra_data",
            "created_at",
        )
        read_only_fields = fields
