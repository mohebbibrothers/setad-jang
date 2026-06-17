"""Django admin configuration for Support Desk."""

from django.contrib import admin

from apps.support_desk.models import (
    SupportBusinessCalendar,
    SupportCannedResponse,
    SupportCategory,
    SupportDepartment,
    SupportDuplicateCandidate,
    SupportHoliday,
    SupportKnowledgeArticle,
    SupportKnowledgeArticleUse,
    SupportSLAEvent,
    SupportSLAPolicy,
    SupportTag,
    SupportTicket,
    SupportTicketAssignment,
    SupportTicketAttachment,
    SupportTicketMessage,
    SupportTicketSatisfaction,
    SupportTicketStatusHistory,
    SupportTicketTag,
    SupportTicketType,
)


class SupportTicketMessageInline(admin.TabularInline):
    """Inline ticket timeline messages for admin inspection."""

    model = SupportTicketMessage
    extra = 0
    fields = ("author", "message_type", "is_internal", "is_from_staff", "body", "created_at")
    readonly_fields = ("created_at",)
    raw_id_fields = ("author",)


class SupportTicketAttachmentInline(admin.TabularInline):
    """Inline support attachments."""

    model = SupportTicketAttachment
    extra = 0
    fields = ("file", "original_filename", "attachment_kind", "visibility", "uploaded_by", "created_at")
    readonly_fields = ("created_at",)
    raw_id_fields = ("uploaded_by",)


class SupportTicketTagInline(admin.TabularInline):
    """Inline ticket tags."""

    model = SupportTicketTag
    extra = 0
    raw_id_fields = ("tag",)


@admin.register(SupportDepartment)
class SupportDepartmentAdmin(admin.ModelAdmin):
    """Admin management for support departments."""

    list_display = ("title", "default_assignee", "order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "slug", "description")
    readonly_fields = ("uuid", "slug", "created_at", "updated_at")
    raw_id_fields = ("default_assignee",)
    ordering = ("order", "title")


@admin.register(SupportCategory)
class SupportCategoryAdmin(admin.ModelAdmin):
    """Admin tree category management."""

    list_display = ("title", "department", "parent", "depth", "order", "is_active", "open_tickets_count")
    list_filter = ("is_active", "department", "depth", "parent")
    search_fields = ("title", "slug", "path", "description")
    readonly_fields = ("slug", "path", "depth", "tickets_count", "open_tickets_count", "created_at", "updated_at")
    raw_id_fields = ("department", "parent")
    ordering = ("depth", "order", "title")


@admin.register(SupportBusinessCalendar)
class SupportBusinessCalendarAdmin(admin.ModelAdmin):
    """Admin business-hours calendar management."""

    list_display = ("title", "department", "timezone_name", "workday_start", "workday_end", "active_weekdays", "is_default", "is_active")
    list_filter = ("is_default", "is_active", "department")
    search_fields = ("title", "timezone_name")
    raw_id_fields = ("department",)


@admin.register(SupportHoliday)
class SupportHolidayAdmin(admin.ModelAdmin):
    """Admin holiday management for support calendars."""

    list_display = ("calendar", "date", "title", "is_active")
    list_filter = ("calendar", "date", "is_active")
    search_fields = ("title",)
    raw_id_fields = ("calendar",)


@admin.register(SupportSLAPolicy)
class SupportSLAPolicyAdmin(admin.ModelAdmin):
    """Admin SLA policy management."""

    list_display = ("title", "department", "priority", "severity", "first_response_minutes", "resolution_minutes", "is_active")
    list_filter = ("priority", "severity", "business_hours_only", "pause_when_waiting_for_user", "escalate_on_breach", "is_active")
    search_fields = ("title", "slug")
    readonly_fields = ("slug", "created_at", "updated_at")
    raw_id_fields = ("department",)
    ordering = ("order", "title")


@admin.register(SupportTicketType)
class SupportTicketTypeAdmin(admin.ModelAdmin):
    """Admin dynamic ticket type/reason management."""

    list_display = ("title", "code", "default_department", "default_category", "default_priority", "default_severity", "is_active")
    list_filter = ("default_priority", "default_severity", "is_active")
    search_fields = ("title", "code", "description")
    raw_id_fields = ("default_department", "default_category", "default_sla_policy")
    ordering = ("order", "title")


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    """Admin ticket queue and detail inspection."""

    list_display = ("ticket_number", "subject", "owner", "department", "status", "priority", "severity", "assigned_to", "last_activity_at")
    list_filter = ("status", "priority", "severity", "department", "ticket_type", "channel")
    search_fields = ("ticket_number", "subject", "description_snapshot", "owner__email", "owner__phone_number")
    readonly_fields = (
        "uuid",
        "ticket_number",
        "search_document",
        "message_count",
        "attachment_count",
        "internal_note_count",
        "reopen_count",
        "created_at",
        "updated_at",
    )
    raw_id_fields = (
        "owner",
        "department",
        "category",
        "ticket_type",
        "assigned_to",
        "escalated_by",
        "applied_sla_policy",
    )
    inlines = [SupportTicketMessageInline, SupportTicketAttachmentInline, SupportTicketTagInline]
    ordering = ("-last_activity_at",)


@admin.register(SupportTicketMessage)
class SupportTicketMessageAdmin(admin.ModelAdmin):
    """Admin timeline message inspection."""

    list_display = ("ticket", "author", "message_type", "is_internal", "is_from_staff", "created_at")
    list_filter = ("message_type", "is_internal", "is_from_staff")
    search_fields = ("ticket__ticket_number", "ticket__subject", "author__email", "body")
    raw_id_fields = ("ticket", "author")


@admin.register(SupportTicketAttachment)
class SupportTicketAttachmentAdmin(admin.ModelAdmin):
    """Admin support attachment inspection."""

    list_display = ("original_filename", "ticket", "uploaded_by", "attachment_kind", "visibility", "file_size", "created_at")
    list_filter = ("attachment_kind", "visibility", "content_type")
    search_fields = ("original_filename", "ticket__ticket_number", "uploaded_by__email")
    raw_id_fields = ("ticket", "message", "uploaded_by")


@admin.register(SupportTag)
class SupportTagAdmin(admin.ModelAdmin):
    """Admin support tag dictionary."""

    list_display = ("name", "normalized_name", "usage_count", "is_active")
    search_fields = ("name", "normalized_name")
    readonly_fields = ("slug", "normalized_name", "usage_count", "created_at", "updated_at")


@admin.register(SupportCannedResponse)
class SupportCannedResponseAdmin(admin.ModelAdmin):
    """Admin canned response management."""

    list_display = ("title", "department", "category", "usage_count", "is_active")
    list_filter = ("department", "category", "is_active")
    search_fields = ("title", "body")
    raw_id_fields = ("department", "category")


@admin.register(SupportTicketAssignment)
class SupportTicketAssignmentAdmin(admin.ModelAdmin):
    """Admin assignment history inspection."""

    list_display = ("ticket", "assigned_by", "from_assignee", "assigned_to", "department", "created_at")
    search_fields = ("ticket__ticket_number", "reason")
    raw_id_fields = ("ticket", "assigned_by", "from_assignee", "assigned_to", "department")


@admin.register(SupportTicketStatusHistory)
class SupportTicketStatusHistoryAdmin(admin.ModelAdmin):
    """Admin status history inspection."""

    list_display = ("ticket", "changed_by", "from_status", "to_status", "created_at")
    list_filter = ("from_status", "to_status")
    search_fields = ("ticket__ticket_number", "reason")
    raw_id_fields = ("ticket", "changed_by")


@admin.register(SupportSLAEvent)
class SupportSLAEventAdmin(admin.ModelAdmin):
    """Admin SLA event inspection."""

    list_display = ("ticket", "event_type", "occurred_at", "created_at")
    list_filter = ("event_type",)
    search_fields = ("ticket__ticket_number",)
    raw_id_fields = ("ticket",)


@admin.register(SupportTicketSatisfaction)
class SupportTicketSatisfactionAdmin(admin.ModelAdmin):
    """Admin satisfaction rating inspection."""

    list_display = ("ticket", "user", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("ticket__ticket_number", "user__email", "comment")
    raw_id_fields = ("ticket", "user")


@admin.register(SupportDuplicateCandidate)
class SupportDuplicateCandidateAdmin(admin.ModelAdmin):
    """Admin duplicate candidate review."""

    list_display = ("ticket", "candidate_ticket", "score", "status", "reviewed_by", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("ticket__ticket_number", "candidate_ticket__ticket_number", "reason")
    raw_id_fields = ("ticket", "candidate_ticket", "reviewed_by")


@admin.register(SupportKnowledgeArticle)
class SupportKnowledgeArticleAdmin(admin.ModelAdmin):
    """Admin management for support knowledge base articles."""

    list_display = ("title", "department", "category", "ticket_type", "status", "usage_count", "published_at", "is_active")
    list_filter = ("status", "department", "category", "ticket_type", "is_active")
    search_fields = ("title", "slug", "summary", "body")
    readonly_fields = ("slug", "usage_count", "published_at", "archived_at", "created_at", "updated_at")
    raw_id_fields = ("department", "category", "ticket_type")
    ordering = ("title",)


@admin.register(SupportKnowledgeArticleUse)
class SupportKnowledgeArticleUseAdmin(admin.ModelAdmin):
    """Read-only admin for support knowledge article usage events."""

    list_display = ("article", "ticket", "used_by", "context", "created_at")
    list_filter = ("context", "article")
    search_fields = ("article__title", "ticket__ticket_number", "used_by__email")
    readonly_fields = [field.name for field in SupportKnowledgeArticleUse._meta.fields]
    raw_id_fields = ("article", "ticket", "used_by")
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Article usage must be recorded by audited API/service workflows."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Article usage evidence is immutable in admin."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Article usage evidence must remain available for support analytics."""
        return False
