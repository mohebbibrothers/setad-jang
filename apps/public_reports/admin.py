"""Django admin configuration for public report subjects and reports.

UX design:
- Reports are the review workspace for their own documentary images.
- ReportAttachment remains a normalized model, but is hidden from the top-level
  admin index and rendered inline inside the report page.
- Report status transitions are performed through the public_reports service
  layer, not by raw status edits, so workflow validation and audit remain intact.
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action

from .choices import ReportStatus
from .models import Report, ReportAttachment, ReportSubject
from .services import InvalidReportStatusTransition, update_report_status


class HiddenFromAdminIndexMixin:
    """Keep inline-only ModelAdmins registered but hidden from the admin index."""

    def get_model_perms(self, request) -> dict[str, bool]:
        """Return no perms so Django omits this model from the admin index."""
        return {}


class ReportAttachmentInline(admin.TabularInline):
    """Read-only documentary images embedded in the report review workspace."""

    model = ReportAttachment
    extra = 0
    can_delete = False
    fields = ("image", "created_at", "updated_at")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:
        """Attachments are submitted by reporters through the public API."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Attachments are review evidence and should not be edited in admin."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Attachments are evidence and must remain available for review."""
        return False


@admin.register(ReportSubject)
class ReportSubjectAdmin(admin.ModelAdmin):
    """Admin workspace for public report subjects/categories."""

    list_display = ("title", "slug", "order", "is_active", "created_at")
    list_editable = ("order", "is_active")
    search_fields = ("title", "slug")
    list_filter = ("is_active",)
    readonly_fields = ("slug", "created_at", "updated_at")
    ordering = ("order", "title")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Service-backed admin review workspace for public reports."""

    list_display = ("id", "full_name", "subject", "status", "attachments_count", "created_at")
    list_filter = ("status", "subject", "created_at")
    search_fields = ("full_name", "phone_number", "description", "admin_note")
    readonly_fields = (
        "full_name",
        "phone_number",
        "subject",
        "description",
        "status",
        "admin_note",
        "submitter_ip",
        "created_at",
        "updated_at",
        "review_panel",
    )
    fieldsets = (
        (
            "اطلاعات گزارش",
            {
                "fields": ("full_name", "phone_number", "subject", "description", "submitter_ip"),
            },
        ),
        (
            "بررسی ادمین",
            {
                "fields": ("review_panel",),
            },
        ),
        (
            "نتیجه بررسی",
            {
                "fields": ("status", "admin_note"),
            },
        ),
        (
            "زمان‌ها",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )
    inlines = [ReportAttachmentInline]
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Reports are submitted through the public reporting endpoint."""
        return False

    @admin.display(description="تعداد مستندات")
    def attachments_count(self, obj: Report) -> int:
        """Return the number of documentary images for list display."""
        return obj.attachments.count()

    @admin.display(description="ثبت بررسی")
    def review_panel(self, obj: Report) -> str:
        """Render service-backed status transition controls."""
        if not obj or not obj.pk:
            return "پس از ذخیره گزارش قابل بررسی است."

        if obj.status in {ReportStatus.APPROVED, ReportStatus.REJECTED}:
            return format_html(
                '<div class="help">این گزارش تعیین تکلیف شده است. وضعیت فعلی: <strong>{}</strong></div>',
                obj.get_status_display(),
            )

        return format_html(
            '<div class="module">'
            '<p class="help">تغییر وضعیت فقط از مسیر سرویس رسمی انجام می‌شود تا state machine و audit درست اجرا شوند.</p>'
            '<label for="id_public_report_admin_note"><strong>یادداشت ادمین</strong></label><br>'
            '<textarea id="id_public_report_admin_note" name="public_report_admin_note" rows="3" style="width: min(100%, 980px);"></textarea>'
            '<div style="margin-top: 1rem; display: flex; gap: .5rem; flex-wrap: wrap;">'
            '<button type="submit" name="_public_report_mark_reviewing" value="1">در حال بررسی</button>'
            '<button type="submit" class="default" name="_public_report_approve" value="1">تأیید گزارش</button>'
            '<button type="submit" name="_public_report_reject" value="1">رد گزارش</button>'
            "</div>"
            "</div>{}",
            "",
        )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """Route status actions before default readonly admin validation."""
        action_to_status = {
            "_public_report_mark_reviewing": ReportStatus.REVIEWING,
            "_public_report_approve": ReportStatus.APPROVED,
            "_public_report_reject": ReportStatus.REJECTED,
        }
        if request.method == "POST":
            selected_status = next(
                (status for action, status in action_to_status.items() if action in request.POST),
                None,
            )
            if selected_status is not None:
                obj = self.get_object(request, object_id)
                if obj is None:
                    messages.error(request, "گزارش یافت نشد.")
                    return HttpResponseRedirect(request.path)
                return self._handle_status_update(
                    request=request, report=obj, new_status=selected_status
                )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def _handle_status_update(self, *, request, report: Report, new_status: str):
        """Apply one report status transition through the official service."""
        old_status = report.status
        try:
            updated = update_report_status(
                report=report,
                status=new_status,
                admin_note=request.POST.get("public_report_admin_note", ""),
            )
        except InvalidReportStatusTransition as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(request.path)

        log_action(
            user_id=request.user.pk,
            action=audit_actions.REPORT_STATUS_CHANGED,
            resource_type="report",
            resource_id=str(updated.pk),
            changes={"status": {"before": old_status, "after": new_status}},
            **extract_audit_metadata(request),
        )
        messages.success(request, "وضعیت گزارش با موفقیت از مسیر رسمی سرویس بروزرسانی شد.")
        return HttpResponseRedirect(request.path)


@admin.register(ReportAttachment)
class ReportAttachmentAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    """Direct attachment admin, hidden from index because attachments live on Report."""

    list_display = ("report", "created_at")
    search_fields = ("report__full_name", "report__description")
    raw_id_fields = ("report",)
    readonly_fields = ("report", "image", "created_at", "updated_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Attachments are created through public report submission."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Attachments are evidence and should not be edited in admin."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Attachments must remain available for report review."""
        return False
