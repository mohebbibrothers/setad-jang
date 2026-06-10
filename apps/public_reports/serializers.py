"""
DRF serializers for public report public and admin APIs.
"""

from rest_framework import serializers

from .choices import ReportStatus
from .models import Report, ReportAttachment, ReportSubject
from .validators import (
    MAX_ATTACHMENTS_PER_REPORT,
    validate_image_extension,
    validate_image_size,
)

# ============================================================
# Subject Serializers
# ============================================================


class ReportSubjectPublicSerializer(serializers.ModelSerializer):
    """نمایش موضوعات برای کاربر عمومی (فقط فعال‌ها)."""

    class Meta:
        model = ReportSubject
        fields = ("id", "title", "slug", "description", "order")


class ReportSubjectAdminSerializer(serializers.ModelSerializer):
    """نمایش موضوعات برای ادمین به همراه تعداد گزارش‌ها."""

    reports_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReportSubject
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "order",
            "is_active",
            "reports_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "reports_count", "created_at", "updated_at")


class ReportSubjectCreateSerializer(serializers.Serializer):
    """ReportSubjectCreateSerializer implementation for the public_reports application."""
    title = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False, default=0)


class ReportSubjectUpdateSerializer(serializers.Serializer):
    """ReportSubjectUpdateSerializer implementation for the public_reports application."""
    title = serializers.CharField(max_length=150, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)


# ============================================================
# Attachment Serializer
# ============================================================


class ReportAttachmentSerializer(serializers.ModelSerializer):
    """ReportAttachmentSerializer implementation for the public_reports application."""
    class Meta:
        model = ReportAttachment
        fields = ("id", "image", "created_at")


# ============================================================
# Report Serializers
# ============================================================


class ReportCreateSerializer(serializers.Serializer):
    """ReportCreateSerializer implementation for the public_reports application."""
    full_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    subject_id = serializers.PrimaryKeyRelatedField(
        queryset=ReportSubject.objects.all(),
        source="subject",
    )
    description = serializers.CharField()
    attachments = serializers.ListField(
        child=serializers.ImageField(validators=[validate_image_extension, validate_image_size]),
        required=False,
        allow_empty=True,
        max_length=MAX_ATTACHMENTS_PER_REPORT,
    )

    def validate_attachments(self, value):
        if value and len(value) > MAX_ATTACHMENTS_PER_REPORT:
            raise serializers.ValidationError(
                f"حداکثر {MAX_ATTACHMENTS_PER_REPORT} تصویر می‌توانید آپلود کنید."
            )
        return value


class ReportListSerializer(serializers.ModelSerializer):
    """ReportListSerializer implementation for the public_reports application."""
    subject = ReportSubjectPublicSerializer(read_only=True)

    class Meta:
        model = Report
        fields = (
            "id",
            "full_name",
            "subject",
            "status",
            "created_at",
        )


class ReportDetailSerializer(serializers.ModelSerializer):
    """ReportDetailSerializer implementation for the public_reports application."""
    subject = ReportSubjectPublicSerializer(read_only=True)
    attachments = ReportAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Report
        fields = (
            "id",
            "full_name",
            "phone_number",
            "subject",
            "description",
            "status",
            "admin_note",
            "attachments",
            "submitter_ip",
            "created_at",
            "updated_at",
        )


class ReportStatusUpdateSerializer(serializers.Serializer):
    """ReportStatusUpdateSerializer implementation for the public_reports application."""
    status = serializers.ChoiceField(choices=ReportStatus.choices)
    admin_note = serializers.CharField(required=False, allow_blank=True)
