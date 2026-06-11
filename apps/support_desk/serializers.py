"""DRF serializers for Support Desk."""

from rest_framework import serializers

from apps.support_desk.choices import AttachmentKind, AttachmentVisibility
from apps.support_desk.models import (
    SupportCategory,
    SupportDepartment,
    SupportSLAPolicy,
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketMessage,
    SupportTicketType,
)


class SupportDepartmentSerializer(serializers.ModelSerializer):
    """Public department serializer for support routing."""

    class Meta:
        model = SupportDepartment
        fields = ("id", "uuid", "title", "slug", "description", "order")
        read_only_fields = fields


class SupportCategorySerializer(serializers.ModelSerializer):
    """Public support tree category serializer."""

    department = SupportDepartmentSerializer(read_only=True)

    class Meta:
        model = SupportCategory
        fields = ("id", "parent_id", "department", "title", "slug", "path", "depth", "description", "icon", "order")
        read_only_fields = fields


class SupportSLAPolicySummarySerializer(serializers.ModelSerializer):
    """Safe SLA summary serializer."""

    class Meta:
        model = SupportSLAPolicy
        fields = ("id", "title", "first_response_minutes", "resolution_minutes", "pause_when_waiting_for_user")
        read_only_fields = fields


class SupportTicketTypeSerializer(serializers.ModelSerializer):
    """Public dynamic ticket type serializer."""

    default_department = SupportDepartmentSerializer(read_only=True)
    default_category = SupportCategorySerializer(read_only=True)
    default_sla_policy = SupportSLAPolicySummarySerializer(read_only=True)

    class Meta:
        model = SupportTicketType
        fields = (
            "id",
            "code",
            "title",
            "description",
            "default_department",
            "default_category",
            "default_priority",
            "default_severity",
            "default_sla_policy",
            "order",
        )
        read_only_fields = fields


class SupportTicketMessageSerializer(serializers.ModelSerializer):
    """User-safe public timeline message serializer."""

    author_display = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicketMessage
        fields = ("id", "message_type", "body", "is_from_staff", "author_display", "created_at", "edited_at")
        read_only_fields = fields

    def get_author_display(self, obj: SupportTicketMessage) -> str:
        """Return safe display name for a message author."""
        return getattr(obj.author, "full_name", "") or str(obj.author)


class SupportTicketAttachmentSerializer(serializers.ModelSerializer):
    """User-safe support attachment serializer."""

    uploaded_by_display = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicketAttachment
        fields = (
            "id",
            "file",
            "original_filename",
            "content_type",
            "file_size",
            "attachment_kind",
            "visibility",
            "uploaded_by_display",
            "created_at",
        )
        read_only_fields = fields

    def get_uploaded_by_display(self, obj: SupportTicketAttachment) -> str:
        """Return safe uploader display name."""
        return getattr(obj.uploaded_by, "full_name", "") or str(obj.uploaded_by)


class SupportTicketListSerializer(serializers.ModelSerializer):
    """User dashboard ticket card serializer."""

    department = SupportDepartmentSerializer(read_only=True)
    category = SupportCategorySerializer(read_only=True)
    ticket_type = SupportTicketTypeSerializer(read_only=True)

    class Meta:
        model = SupportTicket
        fields = (
            "id",
            "uuid",
            "ticket_number",
            "subject",
            "status",
            "priority",
            "severity",
            "department",
            "category",
            "ticket_type",
            "submitted_at",
            "last_activity_at",
            "first_response_due_at",
            "resolution_due_at",
            "sla_breached_at",
            "message_count",
            "attachment_count",
            "reopen_count",
            "satisfaction_rating_snapshot",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SupportTicketDetailSerializer(SupportTicketListSerializer):
    """User-safe ticket detail serializer with public timeline and attachments."""

    messages = SupportTicketMessageSerializer(many=True, read_only=True)
    attachments = SupportTicketAttachmentSerializer(many=True, read_only=True)
    is_reopenable = serializers.BooleanField(read_only=True)

    class Meta(SupportTicketListSerializer.Meta):
        fields = (
            *SupportTicketListSerializer.Meta.fields,
            "description_snapshot",
            "assigned_to_id",
            "first_admin_response_at",
            "resolved_at",
            "closed_at",
            "reopened_at",
            "sla_total_paused_seconds",
            "is_reopenable",
            "messages",
            "attachments",
        )
        read_only_fields = fields


class SupportTicketCreateUpdateSerializer(serializers.Serializer):
    """Input serializer for creating/updating user tickets."""

    ticket_type_id = serializers.PrimaryKeyRelatedField(queryset=SupportTicketType.objects.all(), source="ticket_type")
    category_id = serializers.PrimaryKeyRelatedField(queryset=SupportCategory.objects.all(), source="category", required=False, allow_null=True)
    subject = serializers.CharField(max_length=260)
    description = serializers.CharField()

    def validate_subject(self, value: str) -> str:
        """Require meaningful ticket subject."""
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError("موضوع تیکت باید حداقل ۵ کاراکتر باشد.")
        return value

    def validate_description(self, value: str) -> str:
        """Require meaningful ticket description."""
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("توضیحات تیکت باید حداقل ۱۰ کاراکتر باشد.")
        return value


class SupportTicketReplySerializer(serializers.Serializer):
    """Input serializer for user replies."""

    body = serializers.CharField()

    def validate_body(self, value: str) -> str:
        """Require meaningful reply body."""
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("متن پاسخ بیش از حد کوتاه است.")
        return value


class SupportTicketAttachmentCreateSerializer(serializers.Serializer):
    """Input serializer for user attachment upload."""

    file = serializers.FileField()
    attachment_kind = serializers.ChoiceField(choices=AttachmentKind.choices, required=False, default=AttachmentKind.OTHER)


class SupportTicketSatisfactionCreateSerializer(serializers.Serializer):
    """Input serializer for ticket satisfaction rating."""

    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class SupportTicketReopenSerializer(serializers.Serializer):
    """Input serializer for reopening a ticket."""

    reason = serializers.CharField(required=False, allow_blank=True, default="")


class SupportTicketSuggestSerializer(serializers.Serializer):
    """Input serializer for smart triage suggestions."""

    subject = serializers.CharField(max_length=260)
    description = serializers.CharField()
    category_id = serializers.PrimaryKeyRelatedField(queryset=SupportCategory.objects.all(), source="category", required=False, allow_null=True)
    ticket_type_id = serializers.PrimaryKeyRelatedField(queryset=SupportTicketType.objects.all(), source="ticket_type", required=False, allow_null=True)


class SupportTriageSuggestionSerializer(serializers.Serializer):
    """Output serializer for smart triage suggestions."""

    department = SupportDepartmentSerializer(allow_null=True)
    category = SupportCategorySerializer(allow_null=True)
    ticket_type = SupportTicketTypeSerializer(allow_null=True)
    priority = serializers.CharField()
    severity = serializers.CharField()
    sla_policy = SupportSLAPolicySummarySerializer(allow_null=True)
    duplicate_warning = serializers.BooleanField()
    similar_ticket_ids = serializers.ListField(child=serializers.IntegerField())
    reason_codes = serializers.ListField(child=serializers.CharField())
    score = serializers.IntegerField()


class SupportAttachmentVisibilityGuardSerializer(serializers.Serializer):
    """Schema-only serializer documenting user upload visibility boundary."""

    visibility = serializers.ChoiceField(choices=AttachmentVisibility.choices, default=AttachmentVisibility.PUBLIC)
