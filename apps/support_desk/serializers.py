"""DRF serializers for Support Desk."""

from rest_framework import serializers

from apps.support_desk.choices import (
    AttachmentKind,
    AttachmentVisibility,
    KnowledgeArticleStatus,
    TicketStatus,
)
from apps.support_desk.models import (
    SupportBusinessCalendar,
    SupportCannedResponse,
    SupportCategory,
    SupportDepartment,
    SupportDuplicateCandidate,
    SupportHoliday,
    SupportKnowledgeArticle,
    SupportKnowledgeArticleUse,
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
        fields = ("id", "uuid", "title", "slug", "description", "order", "is_active")
        read_only_fields = fields


class SupportDepartmentInputSerializer(serializers.Serializer):
    """Admin input serializer for departments."""

    title = serializers.CharField(max_length=180)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    default_assignee_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment._meta.get_field("default_assignee").remote_field.model.objects.all(), source="default_assignee", required=False, allow_null=True)
    order = serializers.IntegerField(required=False, min_value=0, default=0)
    is_active = serializers.BooleanField(required=False)

    def validate_title(self, value: str) -> str:
        """Normalize department title."""
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("عنوان دپارتمان باید حداقل ۲ کاراکتر باشد.")
        return value


class SupportBusinessCalendarSerializer(serializers.ModelSerializer):
    """Admin business-hours calendar serializer."""

    department = SupportDepartmentSerializer(read_only=True)

    class Meta:
        model = SupportBusinessCalendar
        fields = ("id", "title", "department", "timezone_name", "workday_start", "workday_end", "active_weekdays", "is_default", "is_active", "created_at", "updated_at")
        read_only_fields = fields


class SupportBusinessCalendarInputSerializer(serializers.Serializer):
    """Admin input serializer for business calendars."""

    title = serializers.CharField(max_length=180)
    department_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment.all_objects.all(), source="department", required=False, allow_null=True)
    timezone_name = serializers.CharField(max_length=80, required=False, default="Asia/Tehran")
    workday_start = serializers.TimeField(required=False)
    workday_end = serializers.TimeField(required=False)
    active_weekdays = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), required=False)
    is_default = serializers.BooleanField(required=False, default=False)
    is_active = serializers.BooleanField(required=False)


class SupportHolidaySerializer(serializers.ModelSerializer):
    """Admin support holiday serializer."""

    calendar = SupportBusinessCalendarSerializer(read_only=True)

    class Meta:
        model = SupportHoliday
        fields = ("id", "calendar", "date", "title", "is_active", "created_at", "updated_at")
        read_only_fields = fields


class SupportHolidayInputSerializer(serializers.Serializer):
    """Admin input serializer for support holidays."""

    calendar_id = serializers.PrimaryKeyRelatedField(queryset=SupportBusinessCalendar.objects.all(), source="calendar")
    date = serializers.DateField()
    title = serializers.CharField(max_length=180)
    is_active = serializers.BooleanField(required=False)


class SupportCategorySerializer(serializers.ModelSerializer):
    """Public support tree category serializer."""

    department = SupportDepartmentSerializer(read_only=True)

    class Meta:
        model = SupportCategory
        fields = ("id", "parent_id", "department", "title", "slug", "path", "depth", "description", "icon", "order", "is_active")
        read_only_fields = fields


class SupportCategoryInputSerializer(serializers.Serializer):
    """Admin input serializer for support tree categories."""

    department_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment.all_objects.all(), source="department")
    parent_id = serializers.PrimaryKeyRelatedField(queryset=SupportCategory.all_objects.all(), source="parent", required=False, allow_null=True)
    title = serializers.CharField(max_length=180)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    icon = serializers.CharField(required=False, allow_blank=True, default="", max_length=80)
    order = serializers.IntegerField(required=False, min_value=0, default=0)
    is_active = serializers.BooleanField(required=False)

    def validate_title(self, value: str) -> str:
        """Normalize category title."""
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("عنوان دسته‌بندی باید حداقل ۲ کاراکتر باشد.")
        return value


class SupportSLAPolicySummarySerializer(serializers.ModelSerializer):
    """Safe SLA summary serializer."""

    class Meta:
        model = SupportSLAPolicy
        fields = ("id", "title", "first_response_minutes", "resolution_minutes", "pause_when_waiting_for_user", "is_active")
        read_only_fields = fields


class SupportSLAPolicySerializer(serializers.ModelSerializer):
    """Admin SLA policy serializer."""

    department = SupportDepartmentSerializer(read_only=True)

    class Meta:
        model = SupportSLAPolicy
        fields = (
            "id",
            "title",
            "slug",
            "department",
            "priority",
            "severity",
            "first_response_minutes",
            "resolution_minutes",
            "business_hours_only",
            "pause_when_waiting_for_user",
            "escalate_on_breach",
            "order",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SupportSLAPolicyInputSerializer(serializers.Serializer):
    """Admin input serializer for SLA policies."""

    title = serializers.CharField(max_length=180)
    department_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment.all_objects.all(), source="department", required=False, allow_null=True)
    priority = serializers.CharField(required=False, default="normal")
    severity = serializers.CharField(required=False, default="minor")
    first_response_minutes = serializers.IntegerField(min_value=1, required=False, default=24 * 60)
    resolution_minutes = serializers.IntegerField(min_value=1, required=False, default=72 * 60)
    business_hours_only = serializers.BooleanField(required=False, default=False)
    pause_when_waiting_for_user = serializers.BooleanField(required=False, default=True)
    escalate_on_breach = serializers.BooleanField(required=False, default=True)
    order = serializers.IntegerField(required=False, min_value=0, default=0)
    is_active = serializers.BooleanField(required=False)


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
            "is_active",
        )
        read_only_fields = fields


class SupportTicketTypeInputSerializer(serializers.Serializer):
    """Admin input serializer for dynamic ticket types."""

    code = serializers.SlugField(max_length=80)
    title = serializers.CharField(max_length=180)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    default_department_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment.all_objects.all(), source="default_department", required=False, allow_null=True)
    default_category_id = serializers.PrimaryKeyRelatedField(queryset=SupportCategory.all_objects.all(), source="default_category", required=False, allow_null=True)
    default_priority = serializers.CharField(required=False, default="normal")
    default_severity = serializers.CharField(required=False, default="minor")
    default_sla_policy_id = serializers.PrimaryKeyRelatedField(queryset=SupportSLAPolicy.all_objects.all(), source="default_sla_policy", required=False, allow_null=True)
    order = serializers.IntegerField(required=False, min_value=0, default=0)
    is_active = serializers.BooleanField(required=False)


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


class SupportAdminTicketMessageSerializer(SupportTicketMessageSerializer):
    """Admin timeline serializer including internal note visibility."""

    class Meta(SupportTicketMessageSerializer.Meta):
        fields = (*SupportTicketMessageSerializer.Meta.fields, "author_id", "is_internal", "metadata")
        read_only_fields = fields


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


class SupportAdminTicketDetailSerializer(SupportTicketDetailSerializer):
    """Admin ticket detail serializer including internal timeline data."""

    messages = SupportAdminTicketMessageSerializer(many=True, read_only=True)

    class Meta(SupportTicketDetailSerializer.Meta):
        fields = (
            *SupportTicketDetailSerializer.Meta.fields,
            "owner_id",
            "assigned_to_id",
            "applied_sla_policy_id",
            "internal_note_count",
            "escalated_at",
            "escalated_by_id",
            "escalation_reason",
            "search_document",
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
    """Input serializer for user/admin replies."""

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


class SupportAdminAssignSerializer(serializers.Serializer):
    """Admin input serializer for assignment."""

    assignee_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment._meta.get_field("default_assignee").remote_field.model.objects.all(), source="assignee", required=False, allow_null=True)
    department_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment.all_objects.all(), source="department", required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class SupportAdminStatusSerializer(serializers.Serializer):
    """Admin input serializer for status changes."""

    status = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_status(self, value: str) -> str:
        """Validate ticket status without schema enum collisions."""
        if value not in TicketStatus.values:
            raise serializers.ValidationError("وضعیت تیکت نامعتبر است.")
        return value


class SupportAdminReasonSerializer(serializers.Serializer):
    """Admin input serializer for reason-based actions."""

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


class SupportCannedResponseSerializer(serializers.ModelSerializer):
    """Admin canned response serializer."""

    department = SupportDepartmentSerializer(read_only=True)
    category = SupportCategorySerializer(read_only=True)

    class Meta:
        model = SupportCannedResponse
        fields = ("id", "department", "category", "title", "body", "usage_count", "is_active", "created_at", "updated_at")
        read_only_fields = fields


class SupportCannedResponseInputSerializer(serializers.Serializer):
    """Admin input serializer for canned responses."""

    department_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment.all_objects.all(), source="department", required=False, allow_null=True)
    category_id = serializers.PrimaryKeyRelatedField(queryset=SupportCategory.all_objects.all(), source="category", required=False, allow_null=True)
    title = serializers.CharField(max_length=180)
    body = serializers.CharField()
    is_active = serializers.BooleanField(required=False)


class SupportDuplicateCandidateSerializer(serializers.ModelSerializer):
    """Admin duplicate candidate serializer."""

    ticket_number = serializers.CharField(source="ticket.ticket_number", read_only=True)
    candidate_ticket_number = serializers.CharField(source="candidate_ticket.ticket_number", read_only=True)

    class Meta:
        model = SupportDuplicateCandidate
        fields = ("id", "ticket_id", "ticket_number", "candidate_ticket_id", "candidate_ticket_number", "score", "reason", "status", "reviewed_by_id", "reviewed_at", "created_at")
        read_only_fields = fields


class SupportDuplicateReviewSerializer(serializers.Serializer):
    """Admin duplicate review input serializer."""

    status = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class SupportAdminAnalyticsSerializer(serializers.Serializer):
    """Admin support analytics dashboard serializer."""

    total_tickets = serializers.IntegerField()
    open_tickets = serializers.IntegerField()
    unassigned_tickets = serializers.IntegerField()
    sla_breached_tickets = serializers.IntegerField()
    resolved_tickets = serializers.IntegerField()
    escalated_tickets = serializers.IntegerField()
    reopened_tickets = serializers.IntegerField()
    csat_average = serializers.FloatField()
    csat_count = serializers.IntegerField()
    reopen_rate_percent = serializers.FloatField()
    escalation_rate_percent = serializers.FloatField()
    sla_breach_rate_percent = serializers.FloatField()
    status_distribution = serializers.ListField(child=serializers.DictField())
    department_distribution = serializers.ListField(child=serializers.DictField())
    category_distribution = serializers.ListField(child=serializers.DictField())
    ticket_type_distribution = serializers.ListField(child=serializers.DictField())
    priority_distribution = serializers.ListField(child=serializers.DictField())
    severity_distribution = serializers.ListField(child=serializers.DictField())
    assignee_distribution = serializers.ListField(child=serializers.DictField())
    csat_distribution = serializers.ListField(child=serializers.DictField())
    generated_at = serializers.DateTimeField()


class SupportAttachmentVisibilityGuardSerializer(serializers.Serializer):
    """Schema-only serializer documenting user upload visibility boundary."""

    visibility = serializers.ChoiceField(choices=AttachmentVisibility.choices, default=AttachmentVisibility.PUBLIC)


class SupportAssignmentCandidateSerializer(serializers.Serializer):
    """One candidate in support load-balancing recommendation."""

    user_id = serializers.IntegerField(read_only=True)
    user_email = serializers.CharField(read_only=True)
    user_display_name = serializers.CharField(read_only=True)
    workload_score = serializers.IntegerField(read_only=True)
    open_tickets = serializers.IntegerField(read_only=True)
    urgent_or_critical_tickets = serializers.IntegerField(read_only=True)
    breached_sla_tickets = serializers.IntegerField(read_only=True)
    waiting_admin_tickets = serializers.IntegerField(read_only=True)
    department_open_tickets = serializers.IntegerField(read_only=True)
    reason_codes = serializers.ListField(child=serializers.CharField(), read_only=True)


class SupportAssignmentRecommendationSerializer(serializers.Serializer):
    """Load-balanced assignment recommendation payload."""

    ticket_number = serializers.CharField(read_only=True)
    recommended_assignee_id = serializers.IntegerField(read_only=True, allow_null=True)
    recommended_assignee_email = serializers.CharField(read_only=True, allow_blank=True)
    policy_version = serializers.CharField(read_only=True)
    reason_codes = serializers.ListField(child=serializers.CharField(), read_only=True)
    candidates = SupportAssignmentCandidateSerializer(many=True, read_only=True)


class SupportKnowledgeArticleSerializer(serializers.ModelSerializer):
    """Read serializer for support knowledge base articles."""

    department = SupportDepartmentSerializer(read_only=True)
    category = SupportCategorySerializer(read_only=True)
    ticket_type = SupportTicketTypeSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SupportKnowledgeArticle
        fields = (
            "id",
            "department",
            "category",
            "ticket_type",
            "title",
            "slug",
            "summary",
            "body",
            "keywords",
            "status",
            "status_display",
            "published_at",
            "archived_at",
            "usage_count",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SupportKnowledgeArticleInputSerializer(serializers.Serializer):
    """Admin input serializer for support knowledge base articles."""

    department_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment.all_objects.all(), source="department", required=False, allow_null=True)
    category_id = serializers.PrimaryKeyRelatedField(queryset=SupportCategory.all_objects.all(), source="category", required=False, allow_null=True)
    ticket_type_id = serializers.PrimaryKeyRelatedField(queryset=SupportTicketType.all_objects.all(), source="ticket_type", required=False, allow_null=True)
    title = serializers.CharField(max_length=220)
    summary = serializers.CharField(required=False, allow_blank=True, default="")
    body = serializers.CharField()
    keywords = serializers.ListField(child=serializers.CharField(max_length=60), required=False, default=list)
    status = serializers.ChoiceField(choices=KnowledgeArticleStatus.choices, required=False, default=KnowledgeArticleStatus.DRAFT)
    is_active = serializers.BooleanField(required=False)


class SupportKnowledgeArticleUseSerializer(serializers.ModelSerializer):
    """Read serializer for knowledge article usage events."""

    article_title = serializers.CharField(source="article.title", read_only=True)
    ticket_number = serializers.CharField(source="ticket.ticket_number", read_only=True, allow_null=True)

    class Meta:
        model = SupportKnowledgeArticleUse
        fields = ("id", "article", "article_title", "ticket", "ticket_number", "used_by", "context", "metadata", "created_at")
        read_only_fields = fields


class SupportKnowledgeArticleUseInputSerializer(serializers.Serializer):
    """Input serializer for recording article usage in support context."""

    ticket_number = serializers.CharField(required=False, allow_blank=True, default="")
    context = serializers.CharField(required=False, allow_blank=True, default="reply", max_length=40)


class SupportKnowledgeRecommendationSerializer(serializers.Serializer):
    """Input serializer for knowledge article recommendation."""

    subject = serializers.CharField(max_length=260)
    description = serializers.CharField()
    department_id = serializers.PrimaryKeyRelatedField(queryset=SupportDepartment.objects.all(), source="department", required=False, allow_null=True)
    category_id = serializers.PrimaryKeyRelatedField(queryset=SupportCategory.objects.all(), source="category", required=False, allow_null=True)
    ticket_type_id = serializers.PrimaryKeyRelatedField(queryset=SupportTicketType.objects.all(), source="ticket_type", required=False, allow_null=True)
