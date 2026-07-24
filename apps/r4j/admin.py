"""
Django Admin اپ R4J.

طراحی UX:
- «مجرمان» مرکز اصلی ورود/ویرایش اطلاعات پروفایل است.
- داده‌های وابسته‌ی مستقیم به مجرم (alias/phone/social/photo/attachment/visibility)
  به‌صورت inline داخل صفحه مجرم مدیریت می‌شوند تا ادمین برای ثبت یک پروفایل
  بین چند صفحه پراکنده نچرخد.
- مدل‌های وابسته همچنان جدا و relational باقی می‌مانند، اما بعضی از آن‌ها از
  index اصلی ادمین مخفی می‌شوند تا هم معماری دیتابیس تمیز بماند، هم UX خلوت‌تر شود.
- مدل‌های workflow مستقل مثل گزارش‌ها، جوایز و chain-of-custody در index باقی
  می‌مانند چون queue/review/filter مستقل دارند.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html, format_html_join

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.r4j.choices import PublicVisibilityField, ReportFieldChangeStatus, ReportStatus

from . import services
from .models import (
    R4JBounty,
    R4JCriminal,
    R4JCriminalAlias,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JCriminalPhone,
    R4JCriminalPhoto,
    R4JCriminalSocial,
    R4JEvidenceCustodyEvent,
    R4JReport,
    R4JReportAliasSuggestion,
    R4JReportAttachment,
    R4JReportFieldChange,
    R4JReportPhoneSuggestion,
    R4JReportSocialSuggestion,
)


class HiddenFromAdminIndexMixin:
    """Keep a ModelAdmin registered but hide it from the admin index/app list."""

    def get_model_perms(self, request) -> dict[str, bool]:
        """Return no perms so Django omits this model from the admin index."""
        return {}




class R4JCriminalFieldVisibilityAdminForm(forms.ModelForm):
    """Persian, dropdown-based form for per-criminal public field visibility rules."""

    class Meta:
        model = R4JCriminalFieldVisibility
        fields = ("criminal", "field_name", "is_public", "is_active")
        labels = {
            "field_name": "فیلد اطلاعاتی",
            "is_public": "در سایت نمایش داده شود؟",
            "is_active": "این قانون فعال باشد؟",
        }
        help_texts = {
            "field_name": "به‌جای تایپ فنی، فیلدی را انتخاب کنید که نمایش عمومی‌اش برای این مجرم تغییر کند.",
            "is_public": "اگر خاموش باشد، این فیلد در صفحه عمومی این مجرم مخفی می‌شود.",
            "is_active": "اگر خاموش باشد، این قانون نادیده گرفته می‌شود و پیش‌فرض سیستم اعمال می‌شود.",
        }
        widgets = {
            "field_name": forms.Select(choices=PublicVisibilityField.choices),
        }


class R4JCriminalAliasInline(admin.TabularInline):
    """Inline aliases inside the criminal edit page."""

    model = R4JCriminalAlias
    extra = 0
    fields = ("alias", "is_active")
    show_change_link = False


class R4JCriminalPhoneInline(admin.TabularInline):
    """Inline phone numbers inside the criminal edit page."""

    model = R4JCriminalPhone
    extra = 0
    fields = ("label", "number", "is_public", "notes", "is_active")
    show_change_link = False


class R4JCriminalSocialInline(admin.TabularInline):
    """Inline social accounts inside the criminal edit page."""

    model = R4JCriminalSocial
    extra = 0
    fields = ("platform", "handle_or_url", "is_public", "is_active")
    show_change_link = False


class R4JCriminalPhotoInline(admin.TabularInline):
    """Inline criminal photos inside the criminal edit page."""

    model = R4JCriminalPhoto
    extra = 0
    fields = ("image", "caption", "is_primary", "order", "is_active")
    show_change_link = False


class R4JCriminalAttachmentInline(admin.TabularInline):
    """Inline profile evidence/documents while preserving forensic metadata."""

    model = R4JCriminalAttachment
    extra = 0
    fields = (
        "file",
        "kind",
        "title",
        "description",
        "is_public",
        "file_sha256",
        "file_size",
        "is_active",
    )
    readonly_fields = ("file_sha256", "file_size")
    show_change_link = True


class R4JCriminalFieldVisibilityInline(admin.TabularInline):
    """Inline, dropdown-based public visibility overrides for one criminal."""

    model = R4JCriminalFieldVisibility
    form = R4JCriminalFieldVisibilityAdminForm
    extra = 0
    fields = ("field_name", "is_public", "is_active")
    show_change_link = False


@admin.register(R4JCriminal)
class R4JCriminalAdmin(admin.ModelAdmin):
    """Main admin workspace for creating and maintaining R4J criminal profiles."""

    list_display = (
        "id",
        "first_name",
        "last_name",
        "slug",
        "is_published",
        "is_active",
        "total_bounty_toman",
        "bounties_count",
        "created_at",
    )
    list_filter = ("is_published", "is_active", "gender", "country", "province")
    search_fields = ("first_name", "last_name", "slug", "national_code", "city")
    readonly_fields = ("slug", "total_bounty_toman", "bounties_count", "published_at")
    fieldsets = (
        ("هویت", {
            "fields": ("first_name", "last_name", "slug", "national_code", "birth_date", "gender"),
        }),
        ("موقعیت", {
            "fields": ("country", "province", "city"),
        }),
        ("توضیحات", {
            "fields": ("description", "crimes_summary", "other_info"),
        }),
        ("انتشار و وضعیت", {
            "fields": ("is_published", "published_at", "is_active"),
        }),
        ("خلاصه جوایز", {
            "fields": ("total_bounty_toman", "bounties_count"),
        }),
    )
    inlines = [
        R4JCriminalAliasInline,
        R4JCriminalPhoneInline,
        R4JCriminalSocialInline,
        R4JCriminalPhotoInline,
        R4JCriminalAttachmentInline,
        R4JCriminalFieldVisibilityInline,
    ]

    def save_formset(self, request, form, formset, change) -> None:
        """Persist inline formsets with R4J-specific safety hooks.

        Attachment inlines need the same forensic guarantees as API-created
        evidence: file hash, size, and chain-of-custody events. Django admin's
        default inline save would bypass the service layer, so we handle this
        model explicitly.
        """
        if formset.model is not R4JCriminalAttachment:
            return super().save_formset(request, form, formset, change)

        deleted_forms = set(formset.deleted_forms)
        for inline_form in formset.forms:
            if inline_form in deleted_forms and inline_form.instance.pk:
                inline_form.instance.delete()

        parent = form.instance
        for inline_form in formset.forms:
            if inline_form in deleted_forms or not inline_form.has_changed():
                continue

            attachment = inline_form.save(commit=False)
            attachment.criminal = parent
            if not attachment.pk and not attachment.uploaded_by_id:
                attachment.uploaded_by = request.user

            file_changed = "file" in inline_form.changed_data
            attachment.save()

            if attachment.file and (file_changed or not attachment.file_sha256):
                services._finalize_evidence_hash(attachment=attachment, actor=request.user)

        formset.save_m2m()


@admin.register(R4JCriminalAttachment)
class R4JCriminalAttachmentAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    """Specialized attachment admin, hidden from index but accessible by direct links."""

    list_display = ("id", "criminal", "kind", "title", "is_public", "uploaded_by", "file_size")
    list_filter = ("kind", "is_public", "is_active")
    search_fields = ("title", "description", "file_sha256", "criminal__first_name", "criminal__last_name")
    readonly_fields = ("file_sha256", "file_size", "created_at", "updated_at")
    raw_id_fields = ("criminal", "uploaded_by")

    def save_model(self, request, obj, form, change) -> None:
        """Keep direct attachment edits safe by recalculating forensic metadata."""
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        file_changed = "file" in form.changed_data
        super().save_model(request, obj, form, change)
        if obj.file and (file_changed or not obj.file_sha256):
            services._finalize_evidence_hash(attachment=obj, actor=request.user)


@admin.register(R4JCriminalFieldVisibility)
class R4JCriminalFieldVisibilityAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    """Visibility override admin, hidden from index because it lives inline on Criminal."""

    form = R4JCriminalFieldVisibilityAdminForm
    list_display = ("id", "criminal", "field_name", "is_public", "is_active")
    list_filter = ("is_public", "field_name", "is_active")
    search_fields = ("criminal__first_name", "criminal__last_name", "field_name")
    raw_id_fields = ("criminal",)


class R4JReportFieldChangeInline(admin.TabularInline):
    """Read-only field-change context plus service-backed review panel on report."""

    model = R4JReportFieldChange
    extra = 0
    can_delete = False
    fields = ("field_name", "current_value_snapshot", "suggested_value", "status", "admin_note")
    readonly_fields = fields
    show_change_link = False

    def has_add_permission(self, request, obj=None) -> bool:
        """Field changes are created through user reports, not manually in admin."""
        return False


class R4JReportAliasSuggestionInline(admin.TabularInline):
    """Read-only alias suggestions visible inside the report review workspace."""

    model = R4JReportAliasSuggestion
    extra = 0
    can_delete = False
    fields = ("alias", "status", "admin_note", "applied_alias")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool: return False


class R4JReportPhoneSuggestionInline(admin.TabularInline):
    """Read-only phone suggestions visible inside the report review workspace."""

    model = R4JReportPhoneSuggestion
    extra = 0
    can_delete = False
    fields = ("label", "number", "is_public", "notes", "status", "admin_note", "applied_phone")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool: return False


class R4JReportSocialSuggestionInline(admin.TabularInline):
    """Read-only social suggestions visible inside the report review workspace."""

    model = R4JReportSocialSuggestion
    extra = 0
    can_delete = False
    fields = ("platform", "handle_or_url", "is_public", "status", "admin_note", "applied_social")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool: return False


class R4JReportAttachmentInline(admin.TabularInline):
    """Read-only report evidence visible inside the report review workspace."""

    model = R4JReportAttachment
    extra = 0
    can_delete = False
    fields = ("file", "title", "kind", "status", "admin_note", "file_sha256", "file_size", "promoted_criminal_attachment", "created_at")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:
        """Report attachments are submitted by users and preserved for review."""
        return False


@admin.register(R4JReport)
class R4JReportAdmin(admin.ModelAdmin):
    """Service-backed admin workspace for reviewing one user report in context."""

    list_display = (
        "id",
        "criminal",
        "submitted_by",
        "status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("criminal__first_name", "criminal__last_name", "submitted_by__email", "notes")
    raw_id_fields = ("criminal", "submitted_by", "reviewed_by")
    readonly_fields = (
        "criminal",
        "submitted_by",
        "notes",
        "status",
        "admin_note",
        "reviewed_by",
        "reviewed_at",
        "cancel_requested_at",
        "canceled_at",
        "created_at",
        "updated_at",
        "review_decision_panel",
    )
    fieldsets = (
        ("اطلاعات گزارش", {
            "fields": ("criminal", "submitted_by", "status", "notes"),
        }),
        ("بررسی رسمی", {
            "fields": ("review_decision_panel",),
        }),
        ("نتیجه بررسی", {
            "fields": ("admin_note", "reviewed_by", "reviewed_at", "cancel_requested_at", "canceled_at"),
        }),
        ("زمان‌ها", {
            "fields": ("created_at", "updated_at"),
        }),
    )
    inlines = [
        R4JReportFieldChangeInline,
        R4JReportAliasSuggestionInline,
        R4JReportPhoneSuggestionInline,
        R4JReportSocialSuggestionInline,
        R4JReportAttachmentInline,
    ]

    def has_add_permission(self, request) -> bool:
        """Reports are submitted by users through the R4J public workflow."""
        return False

    @admin.display(description="تصمیم‌گیری و ثبت بررسی")
    def review_decision_panel(self, obj: R4JReport) -> str:
        """Render a compact decision matrix submitted through services.review_report."""
        if not obj or not obj.pk:
            return "پس از ذخیره گزارش قابل بررسی است."

        if obj.status != ReportStatus.PENDING:
            return format_html(
                '<div class="help">این گزارش قبلاً تعیین تکلیف شده است. وضعیت فعلی: <strong>{}</strong></div>',
                obj.get_status_display(),
            )

        field_changes = list(obj.field_changes.all().order_by("id"))
        alias_suggestions = list(obj.alias_suggestions.all().order_by("id"))
        phone_suggestions = list(obj.phone_suggestions.all().order_by("id"))
        social_suggestions = list(obj.social_suggestions.all().order_by("id"))
        attachments = list(obj.attachments.all().order_by("id"))
        has_decision_items = any([field_changes, alias_suggestions, phone_suggestions, social_suggestions, attachments])
        admin_note_input = format_html(
            '<div style="margin-top: 1rem;">'
            '<label for="id_r4j_report_admin_note"><strong>یادداشت کلی ادمین</strong></label><br>'
            '<textarea id="id_r4j_report_admin_note" name="r4j_report_admin_note" rows="3" '
            'style="width: min(100%, 980px);"></textarea>'
            '</div>{}',
            "",
        )
        submit_button = format_html(
            '<div style="margin-top: 1rem;">'
            '<button type="submit" class="default" name="_r4j_review_report" value="1">'
            'ثبت بررسی از مسیر امن سرویس'
            '</button>'
            '</div>{}',
            "",
        )

        if not has_decision_items:
            return format_html(
                '<div class="module aligned">'
                '<p>این گزارش فقط شامل یادداشت آزاد است. با ثبت بررسی، گزارش از مسیر رسمی سرویس تأیید می‌شود.</p>'
                '{}{}'
                '</div>',
                admin_note_input,
                submit_button,
            )

        rows = []

        def append_decision_row(kind: str, label: str, current: str, suggested: str, input_name: str, note_name: str) -> None:
            rows.append(format_html(
                '<tr>'
                '<td><strong>{}</strong><br><code>{}</code></td>'
                '<td style="white-space: pre-wrap; max-width: 280px;">{}</td>'
                '<td style="white-space: pre-wrap; max-width: 320px;">{}</td>'
                '<td>'
                '<select name="{}" required>'
                '<option value="">انتخاب کنید</option>'
                '<option value="{}">تأیید و اعمال</option>'
                '<option value="{}">رد</option>'
                '</select>'
                '</td>'
                '<td><input type="text" name="{}" style="width: 100%;" title="یادداشت اختیاری برای این مورد"></td>'
                '</tr>',
                kind,
                label,
                current,
                suggested,
                input_name,
                ReportFieldChangeStatus.APPROVED,
                ReportFieldChangeStatus.REJECTED,
                note_name,
            ))

        for fc in field_changes:
            append_decision_row(
                "اصلاح فیلد",
                fc.field_name,
                fc.current_value_snapshot,
                fc.suggested_value,
                f"r4j_decision_{fc.pk}",
                f"r4j_note_{fc.pk}",
            )
        for item in alias_suggestions:
            append_decision_row("نام مستعار", f"alias#{item.pk}", "—", item.alias, f"r4j_alias_decision_{item.pk}", f"r4j_alias_note_{item.pk}")
        for item in phone_suggestions:
            append_decision_row("شماره تماس", f"phone#{item.pk}", item.label or "—", item.number, f"r4j_phone_decision_{item.pk}", f"r4j_phone_note_{item.pk}")
        for item in social_suggestions:
            append_decision_row("شبکه اجتماعی", f"social#{item.pk}", item.platform, item.handle_or_url, f"r4j_social_decision_{item.pk}", f"r4j_social_note_{item.pk}")
        for item in attachments:
            append_decision_row("ضمیمه/مدرک", f"attachment#{item.pk}", item.kind, item.title or item.file.name, f"r4j_attachment_decision_{item.pk}", f"r4j_attachment_note_{item.pk}")

        return format_html(
            '<div class="module">'
            '<p class="help">هر پیشنهاد اصلاح را تأیید یا رد کنید. تأییدها فقط از مسیر '
            '<code>services.review_report</code> اعمال می‌شوند تا state machine، تبدیل نوع، audit و cache درست بمانند.</p>'
            '<table style="width: 100%;">'
            '<thead><tr><th>فیلد</th><th>مقدار فعلی هنگام گزارش</th><th>مقدار پیشنهادی</th><th>تصمیم</th><th>یادداشت فیلد</th></tr></thead>'
            '<tbody>{}</tbody>'
            '</table>'
            '{}{}'
            '</div>',
            format_html_join("", "{}", ((row,) for row in rows)),
            admin_note_input,
            submit_button,
        )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """Route review submissions before default admin formset validation.

        The review panel uses custom POST fields, not editable inline formsets.
        Intercepting here prevents unrelated readonly inline management forms from
        blocking the service-backed review action.
        """
        if request.method == "POST" and "_r4j_review_report" in request.POST:
            obj = self.get_object(request, object_id)
            if obj is None:
                messages.error(request, "گزارش یافت نشد.")
                return HttpResponseRedirect(request.path)
            return self._handle_review_request(request, obj)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def _collect_report_decisions(self, *, request, items, post_prefix: str, id_key: str, missing_decisions: list[str], label_getter) -> list[dict[str, str | int]]:
        """Collect approve/reject decisions for non-field report suggestions."""
        collected = []
        for item in items:
            decision = request.POST.get(f"{post_prefix}_decision_{item.pk}", "")
            if decision not in {ReportFieldChangeStatus.APPROVED, ReportFieldChangeStatus.REJECTED}:
                missing_decisions.append(label_getter(item))
                continue
            collected.append({
                id_key: item.pk,
                "status": decision,
                "admin_note": request.POST.get(f"{post_prefix}_note_{item.pk}", ""),
            })
        return collected

    def _handle_review_request(self, request, obj: R4JReport):
        """Run the official review service from the Django admin workspace."""
        obj = R4JReport.objects.prefetch_related("field_changes", "alias_suggestions", "phone_suggestions", "social_suggestions", "attachments").get(pk=obj.pk)
        if obj.status != ReportStatus.PENDING:
            messages.error(request, "فقط گزارش‌های در انتظار بررسی قابل بررسی هستند.")
            return HttpResponseRedirect(request.path)

        decisions = []
        missing_decisions: list[str] = []
        for field_change in obj.field_changes.all().order_by("id"):
            decision = request.POST.get(f"r4j_decision_{field_change.pk}", "")
            if decision not in {ReportFieldChangeStatus.APPROVED, ReportFieldChangeStatus.REJECTED}:
                missing_decisions.append(field_change.field_name)
                continue
            decisions.append({
                "field_change_id": field_change.pk,
                "status": decision,
                "admin_note": request.POST.get(f"r4j_note_{field_change.pk}", ""),
            })

        alias_decisions = self._collect_report_decisions(
            request=request,
            items=obj.alias_suggestions.all().order_by("id"),
            post_prefix="r4j_alias",
            id_key="alias_suggestion_id",
            missing_decisions=missing_decisions,
            label_getter=lambda item: f"alias:{item.alias}",
        )
        phone_decisions = self._collect_report_decisions(
            request=request,
            items=obj.phone_suggestions.all().order_by("id"),
            post_prefix="r4j_phone",
            id_key="phone_suggestion_id",
            missing_decisions=missing_decisions,
            label_getter=lambda item: f"phone:{item.number}",
        )
        social_decisions = self._collect_report_decisions(
            request=request,
            items=obj.social_suggestions.all().order_by("id"),
            post_prefix="r4j_social",
            id_key="social_suggestion_id",
            missing_decisions=missing_decisions,
            label_getter=lambda item: f"social:{item.handle_or_url}",
        )
        attachment_decisions = self._collect_report_decisions(
            request=request,
            items=obj.attachments.all().order_by("id"),
            post_prefix="r4j_attachment",
            id_key="attachment_id",
            missing_decisions=missing_decisions,
            label_getter=lambda item: f"attachment:{item.pk}",
        )

        if missing_decisions:
            messages.error(
                request,
                "برای همه پیشنهادهای اصلاح باید تصمیم تأیید یا رد ثبت شود: "
                + ", ".join(missing_decisions),
            )
            return HttpResponseRedirect(request.path)

        try:
            reviewed_report = services.review_report(
                report=obj,
                reviewed_by=request.user,
                field_decisions=decisions,
                alias_decisions=alias_decisions,
                phone_decisions=phone_decisions,
                social_decisions=social_decisions,
                attachment_decisions=attachment_decisions,
                admin_note=request.POST.get("r4j_report_admin_note", ""),
            )
        except services.ReportNotReviewable as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(request.path)

        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.R4J_REPORT_REVIEWED,
            resource_type="r4j_report",
            resource_id=str(reviewed_report.pk),
            extra_data={"final_status": reviewed_report.status, "source": "django_admin"},
            **extract_audit_metadata(request),
        )
        messages.success(request, "گزارش با موفقیت از مسیر رسمی سرویس بررسی شد.")
        return HttpResponseRedirect(request.path)


@admin.register(R4JReportFieldChange)
class R4JReportFieldChangeAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    """Direct field-change admin, hidden from index because review happens on Report."""

    list_display = ("id", "report", "field_name", "status")
    list_filter = ("status", "field_name")
    search_fields = ("field_name", "suggested_value", "current_value_snapshot")
    readonly_fields = ("report", "field_name", "suggested_value", "current_value_snapshot", "status", "admin_note")
    raw_id_fields = ("report",)

    def has_add_permission(self, request) -> bool:
        """Field changes are created by report submission."""
        return False


@admin.register(R4JReportAttachment)
class R4JReportAttachmentAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    """Direct report evidence admin, hidden from index because it lives on Report."""

    list_display = ("id", "report", "kind", "title", "file_size")
    list_filter = ("kind",)
    search_fields = ("title", "file_sha256")
    readonly_fields = ("report", "file", "title", "kind", "file_sha256", "file_size", "created_at", "updated_at")
    raw_id_fields = ("report",)

    def has_add_permission(self, request) -> bool:
        """Report attachments are submitted by users and preserved for review."""
        return False


@admin.register(R4JBounty)
class R4JBountyAdmin(admin.ModelAdmin):
    """Admin queue for user bounty commitments and cancel requests."""

    list_display = (
        "id",
        "criminal",
        "user",
        "amount_toman",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "criminal__first_name",
        "criminal__last_name",
        "user__email",
        "user__phone_number",
    )
    raw_id_fields = ("criminal", "user")


@admin.register(R4JEvidenceCustodyEvent)
class R4JEvidenceCustodyEventAdmin(admin.ModelAdmin):
    """Read-only admin for R4J evidence chain-of-custody events."""

    list_display = ("id", "event_type", "file_sha256", "actor", "created_at")
    list_filter = ("event_type",)
    search_fields = ("file_sha256", "actor__email", "note")
    readonly_fields = [field.name for field in R4JEvidenceCustodyEvent._meta.fields]
    raw_id_fields = ("criminal_attachment", "report_attachment", "actor")
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Custody events are generated through audited services."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Custody events are immutable."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Custody events must remain available for forensic review."""
        return False
