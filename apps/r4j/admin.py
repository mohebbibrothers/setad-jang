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

from django.contrib import admin

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
    R4JReportAttachment,
    R4JReportFieldChange,
)


class HiddenFromAdminIndexMixin:
    """Keep a ModelAdmin registered but hide it from the admin index/app list."""

    def get_model_perms(self, request) -> dict[str, bool]:
        """Return no perms so Django omits this model from the admin index."""
        return {}


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
    """Inline per-criminal public visibility overrides."""

    model = R4JCriminalFieldVisibility
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

    list_display = ("id", "criminal", "field_name", "is_public", "is_active")
    list_filter = ("is_public", "field_name", "is_active")
    search_fields = ("criminal__first_name", "criminal__last_name", "field_name")
    raw_id_fields = ("criminal",)


@admin.register(R4JReport)
class R4JReportAdmin(admin.ModelAdmin):
    """Admin queue for user-submitted R4J reports."""

    list_display = (
        "id",
        "criminal",
        "submitted_by",
        "status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("criminal__first_name", "criminal__last_name", "submitted_by__email")
    raw_id_fields = ("criminal", "submitted_by", "reviewed_by")


@admin.register(R4JReportFieldChange)
class R4JReportFieldChangeAdmin(admin.ModelAdmin):
    """Admin visibility for per-field report decisions."""

    list_display = ("id", "report", "field_name", "status")
    list_filter = ("status", "field_name")
    search_fields = ("field_name", "suggested_value", "current_value_snapshot")
    raw_id_fields = ("report",)


@admin.register(R4JReportAttachment)
class R4JReportAttachmentAdmin(admin.ModelAdmin):
    """Admin queue for user-submitted report evidence."""

    list_display = ("id", "report", "kind", "title", "file_size")
    list_filter = ("kind",)
    search_fields = ("title", "file_sha256")
    readonly_fields = ("file_sha256", "file_size", "created_at", "updated_at")
    raw_id_fields = ("report",)


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
