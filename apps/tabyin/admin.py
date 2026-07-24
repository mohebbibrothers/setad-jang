"""Django Admin برای اپ جهاد تبیین.

طراحی UX:
- «محتواهای تبیین» مرکز مشاهده/مدیریت محتوای همگام‌سازی‌شده و وضعیت نمایش است.
- «ارسال‌های کاربران تبیین» یک صف review جدا و service-backed برای محتوای ارسالی کاربران است.
- «پیوست‌های تبیین» مدل جدا و relational باقی می‌ماند، اما از index اصلی ادمین مخفی است و داخل صفحه محتوا/ارسال به‌صورت inline دیده می‌شود.
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.utils.html import format_html

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.tabyin import services
from apps.tabyin.choices import ContentOrigin, SubmissionStatus
from apps.tabyin.models import TabyinAttachment, TabyinContent, TabyinUserSubmission


class HiddenFromAdminIndexMixin:
    """Keep a ModelAdmin registered but hide it from the admin index/app list."""

    def get_model_perms(self, request) -> dict[str, bool]:
        """Return no perms so Django omits this model from the admin index."""
        return {}


class TabyinAttachmentInline(admin.TabularInline):
    """Read-only attachment context embedded in content/submission pages."""

    model = TabyinAttachment
    extra = 0
    can_delete = False
    readonly_fields = (
        "order",
        "media_type",
        "url",
        "relative_url",
        "size",
        "duration",
        "file_size",
        "title",
        "created_at",
        "updated_at",
    )
    fields = (
        "order",
        "media_type",
        "url",
        "size",
        "duration",
        "file_size",
        "title",
    )
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:
        """Attachments are created via sync or user submission APIs."""
        return False


@admin.register(TabyinContent)
class TabyinContentAdmin(admin.ModelAdmin):
    """Admin workspace for synced/approved Tabyin contents and display toggling."""

    list_display = (
        "external_id",
        "title_short",
        "origin",
        "submission_status",
        "author_username",
        "is_active",
        "is_deleted_in_source",
        "attachments_count",
        "source_created_at",
        "last_synced_at",
    )
    list_filter = (
        "origin",
        "submission_status",
        "is_active",
        "is_deleted_in_source",
        "source_type",
    )
    search_fields = (
        "external_id",
        "title",
        "description",
        "author_username",
        "submitted_by__email",
    )
    readonly_fields = (
        "external_id",
        "origin",
        "submitted_by",
        "submission_status",
        "reviewed_by",
        "reviewed_at",
        "admin_note",
        "title",
        "description",
        "author_username",
        "source_entity_id",
        "source_status",
        "source_type",
        "source_created_at",
        "source_updated_at",
        "source_url",
        "content_hash",
        "last_synced_at",
        "is_deleted_in_source",
        "raw_payload",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        ("وضعیت نمایش", {
            "fields": ("is_active", "is_deleted_in_source"),
        }),
        ("محتوا", {
            "fields": ("title", "description", "author_username"),
        }),
        ("منشأ و بررسی", {
            "fields": ("origin", "submitted_by", "submission_status", "reviewed_by", "reviewed_at", "admin_note"),
        }),
        ("اطلاعات منبع خارجی", {
            "fields": (
                "external_id",
                "source_entity_id",
                "source_status",
                "source_type",
                "source_created_at",
                "source_updated_at",
                "source_url",
                "content_hash",
                "last_synced_at",
            ),
        }),
        ("داده خام", {
            "classes": ("collapse",),
            "fields": ("raw_payload",),
        }),
        ("زمان‌ها", {
            "fields": ("created_at", "updated_at"),
        }),
    )
    list_editable = ("is_active",)
    list_per_page = 30
    inlines = [TabyinAttachmentInline]
    actions = ("dispatch_incremental_sync", "dispatch_full_sync")

    def get_queryset(self, request):
        """Use all_objects so admin can inspect inactive/rejected/source-deleted rows."""
        return TabyinContent.all_objects.select_related(
            "submitted_by",
            "reviewed_by",
        ).annotate(_attachments_count=Count("attachments"))

    @admin.display(description="عنوان")
    def title_short(self, obj: TabyinContent) -> str:
        """Compact title for list view."""
        return obj.title[:50] if obj.title else "—"

    @admin.display(description="تعداد پیوست")
    def attachments_count(self, obj: TabyinContent) -> int:
        """Return annotated attachment count without per-row queries."""
        return getattr(obj, "_attachments_count", obj.attachments.count())

    @admin.action(description="اجرای همگام‌سازی افزایشی تبیین")
    def dispatch_incremental_sync(self, request, queryset) -> None:
        """Dispatch incremental sync through the service layer from Django admin."""
        self._dispatch_sync_from_admin(request=request, mode="incremental")

    @admin.action(description="اجرای همگام‌سازی کامل تبیین")
    def dispatch_full_sync(self, request, queryset) -> None:
        """Dispatch full sync through the service layer from Django admin."""
        self._dispatch_sync_from_admin(request=request, mode="full")

    def _dispatch_sync_from_admin(self, *, request, mode: str) -> None:
        metadata = extract_audit_metadata(request)
        task_id = services.dispatch_sync_task(
            mode=mode,
            triggered_by_user_id=request.user.pk,
            request_id=metadata["request_id"],
            dispatch_ip=metadata["ip_address"],
        )
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.TABYIN_SYNC_DISPATCHED,
            resource_type="tabyin_sync",
            resource_id=task_id,
            extra_data={"mode": mode, "source": "django_admin"},
            **metadata,
        )
        messages.success(request, f"همگام‌سازی {mode} در صف اجرا قرار گرفت. task_id={task_id}")


@admin.register(TabyinUserSubmission)
class TabyinUserSubmissionAdmin(admin.ModelAdmin):
    """Dedicated service-backed review queue for user-submitted Tabyin content."""

    list_display = (
        "id",
        "title_short",
        "submitted_by",
        "submission_status",
        "is_active",
        "attachments_count",
        "created_at",
        "reviewed_at",
    )
    list_filter = ("submission_status", "is_active", "created_at")
    search_fields = ("title", "description", "submitted_by__email")
    readonly_fields = (
        "external_id",
        "submitted_by",
        "submission_status",
        "is_active",
        "reviewed_by",
        "reviewed_at",
        "admin_note",
        "title",
        "description",
        "created_at",
        "updated_at",
        "review_panel",
    )
    fieldsets = (
        ("اطلاعات ارسال", {
            "fields": ("title", "description", "submitted_by", "submission_status", "is_active"),
        }),
        ("بررسی ادمین", {
            "fields": ("review_panel",),
        }),
        ("نتیجه بررسی", {
            "fields": ("admin_note", "reviewed_by", "reviewed_at"),
        }),
        ("شناسه و زمان‌ها", {
            "fields": ("external_id", "created_at", "updated_at"),
        }),
    )
    inlines = [TabyinAttachmentInline]
    list_per_page = 30

    def has_add_permission(self, request) -> bool:
        """Submissions are created by authenticated users, not by admins."""
        return False

    def get_queryset(self, request):
        """Show only user-submitted content in the dedicated review queue."""
        return TabyinUserSubmission.all_objects.filter(
            origin=ContentOrigin.USER_SUBMITTED,
        ).select_related("submitted_by", "reviewed_by").annotate(_attachments_count=Count("attachments"))

    @admin.display(description="عنوان")
    def title_short(self, obj: TabyinContent) -> str:
        return obj.title[:60] if obj.title else "—"

    @admin.display(description="تعداد پیوست")
    def attachments_count(self, obj: TabyinContent) -> int:
        return getattr(obj, "_attachments_count", obj.attachments.count())

    @admin.display(description="ثبت بررسی")
    def review_panel(self, obj: TabyinContent) -> str:
        """Render approve/reject buttons backed by the official service layer."""
        if not obj or not obj.pk:
            return "پس از ذخیره محتوا قابل بررسی است."
        if obj.submission_status != SubmissionStatus.PENDING_REVIEW:
            return format_html(
                '<div class="help">این ارسال قبلاً تعیین تکلیف شده است. وضعیت فعلی: <strong>{}</strong></div>',
                obj.get_submission_status_display(),
            )
        return format_html(
            '<div class="module">'
            '<p class="help">تأیید/رد فقط از مسیر سرویس رسمی انجام می‌شود تا audit، notification و cache invalidation درست اجرا شوند.</p>'
            '<label for="id_tabyin_admin_note"><strong>یادداشت ادمین</strong></label><br>'
            '<textarea id="id_tabyin_admin_note" name="tabyin_admin_note" rows="3" style="width: min(100%, 980px);"></textarea>'
            '<div style="margin-top: 1rem; display: flex; gap: .5rem;">'
            '<button type="submit" class="default" name="_tabyin_approve_submission" value="1">تأیید و انتشار</button>'
            '<button type="submit" name="_tabyin_reject_submission" value="1">رد ارسال</button>'
            '</div>'
            '</div>{}',
            "",
        )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """Route review submissions before default admin readonly validation."""
        if request.method == "POST" and (
            "_tabyin_approve_submission" in request.POST or "_tabyin_reject_submission" in request.POST
        ):
            obj = self.get_object(request, object_id)
            if obj is None:
                messages.error(request, "محتوای ارسالی یافت نشد.")
                return HttpResponseRedirect(request.path)
            return self._handle_review_request(request, obj)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def _handle_review_request(self, request, obj: TabyinContent):
        """Approve/reject user submission using official services."""
        obj = TabyinContent.all_objects.get(pk=obj.pk)
        admin_note = request.POST.get("tabyin_admin_note", "")
        try:
            if "_tabyin_approve_submission" in request.POST:
                reviewed = services.approve_user_submission(content=obj, admin=request.user, admin_note=admin_note)
                action = audit_actions.TABYIN_USER_SUBMISSION_APPROVED
                message = "محتوای ارسالی با موفقیت تأیید و منتشر شد."
            else:
                reviewed = services.reject_user_submission(content=obj, admin=request.user, admin_note=admin_note)
                action = audit_actions.TABYIN_USER_SUBMISSION_REJECTED
                message = "محتوای ارسالی رد شد."
        except services.SubmissionNotReviewable as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(request.path)

        log_action_async(
            user_id=request.user.pk,
            action=action,
            resource_type="tabyin_content",
            resource_id=str(reviewed.pk),
            extra_data={"source": "django_admin"},
            **extract_audit_metadata(request),
        )
        messages.success(request, message)
        return HttpResponseRedirect(request.path)


@admin.register(TabyinAttachment)
class TabyinAttachmentAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    """Direct attachment admin, hidden from index because attachments live inline."""

    list_display = (
        "id",
        "content_title",
        "media_type",
        "size",
        "duration",
        "file_size",
        "order",
    )
    list_filter = ("media_type",)
    search_fields = ("content__title", "url", "relative_url")
    raw_id_fields = ("content",)
    readonly_fields = (
        "content",
        "url",
        "relative_url",
        "media_type",
        "size",
        "duration",
        "file_size",
        "title",
        "order",
        "created_at",
        "updated_at",
    )
    list_per_page = 50

    @admin.display(description="محتوا")
    def content_title(self, obj: TabyinAttachment) -> str:
        return obj.content.title[:40] if obj.content.title else obj.content.external_id
