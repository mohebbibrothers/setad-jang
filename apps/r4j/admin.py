"""
Django admin اپ R4J.

برای admin panel سبک و سریع، فقط list_display/filter/search تنظیم شده‌اند.
عملیات business سنگین در admin انجام نمی‌شود — همه‌چیز از طریق سرویس‌ها
و REST APIها کنترل می‌شود.
"""

from __future__ import annotations

from django.contrib import admin

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


class R4JCriminalAliasInline(admin.TabularInline):
    """R4JCriminalAliasInline implementation for the r4j application."""
    model = R4JCriminalAlias
    extra = 0


class R4JCriminalPhoneInline(admin.TabularInline):
    """R4JCriminalPhoneInline implementation for the r4j application."""
    model = R4JCriminalPhone
    extra = 0


class R4JCriminalSocialInline(admin.TabularInline):
    """R4JCriminalSocialInline implementation for the r4j application."""
    model = R4JCriminalSocial
    extra = 0


class R4JCriminalPhotoInline(admin.TabularInline):
    """R4JCriminalPhotoInline implementation for the r4j application."""
    model = R4JCriminalPhoto
    extra = 0


@admin.register(R4JCriminal)
class R4JCriminalAdmin(admin.ModelAdmin):
    """R4JCriminalAdmin implementation for the r4j application."""
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
    inlines = [
        R4JCriminalAliasInline,
        R4JCriminalPhoneInline,
        R4JCriminalSocialInline,
        R4JCriminalPhotoInline,
    ]


@admin.register(R4JCriminalAttachment)
class R4JCriminalAttachmentAdmin(admin.ModelAdmin):
    """R4JCriminalAttachmentAdmin implementation for the r4j application."""
    list_display = ("id", "criminal", "kind", "title", "is_public", "uploaded_by")
    list_filter = ("kind", "is_public")
    search_fields = ("title", "criminal__first_name", "criminal__last_name")


@admin.register(R4JCriminalFieldVisibility)
class R4JCriminalFieldVisibilityAdmin(admin.ModelAdmin):
    """R4JCriminalFieldVisibilityAdmin implementation for the r4j application."""
    list_display = ("id", "criminal", "field_name", "is_public")
    list_filter = ("is_public", "field_name")
    search_fields = ("criminal__first_name", "criminal__last_name", "field_name")


@admin.register(R4JReport)
class R4JReportAdmin(admin.ModelAdmin):
    """R4JReportAdmin implementation for the r4j application."""
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


@admin.register(R4JReportFieldChange)
class R4JReportFieldChangeAdmin(admin.ModelAdmin):
    """R4JReportFieldChangeAdmin implementation for the r4j application."""
    list_display = ("id", "report", "field_name", "status")
    list_filter = ("status", "field_name")
    search_fields = ("field_name",)


@admin.register(R4JReportAttachment)
class R4JReportAttachmentAdmin(admin.ModelAdmin):
    """R4JReportAttachmentAdmin implementation for the r4j application."""
    list_display = ("id", "report", "kind", "title")
    list_filter = ("kind",)
    search_fields = ("title",)


@admin.register(R4JBounty)
class R4JBountyAdmin(admin.ModelAdmin):
    """R4JBountyAdmin implementation for the r4j application."""
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
