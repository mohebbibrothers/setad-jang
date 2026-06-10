"""
Django Admin اپ مددکار.

تنظیمات admin برای مدیریت داخلی توسط superuserها.
نکته: عملیات حساس (مثل publish/close) از طریق API انجام می‌شود — admin فقط
برای CRUD ساده و debug است.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from apps.madadkar.models import (
    Campaign,
    CampaignImage,
    Participation,
    Payment,
    Sponsor,
)

# ---------------------------------------------------------------------------
# Sponsor
# ---------------------------------------------------------------------------

@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    """ادمین مددکاران."""

    list_display = ("name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("slug", "created_at", "updated_at")
    ordering = ("name",)


# ---------------------------------------------------------------------------
# CampaignImage inline
# ---------------------------------------------------------------------------

class CampaignImageInline(admin.TabularInline):
    """نمایش inline تصاویر گالری در صفحه ویرایش Campaign."""

    model = CampaignImage
    extra = 0
    fields = ("image", "alt_text", "display_order", "is_active")
    ordering = ("display_order",)


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    """ادمین حرکت‌ها."""

    list_display = (
        "title",
        "sponsor",
        "status",
        "is_visible",
        "progress_display",
        "purchased_shares",
        "total_shares",
        "created_at",
    )
    list_filter = ("status", "is_visible", "has_deadline", "sponsor")
    search_fields = ("title", "slug", "description")
    readonly_fields = (
        "slug",
        "share_price",
        "purchased_shares",
        "purchased_amount",
        "participant_count",
        "published_at",
        "completed_at",
        "closed_at",
        "created_at",
        "updated_at",
    )
    inlines = [CampaignImageInline]
    ordering = ("-created_at",)

    fieldsets = (
        ("اطلاعات اصلی", {
            "fields": ("sponsor", "title", "slug", "description", "cover_image"),
        }),
        ("مالی", {
            "fields": ("total_amount", "total_shares", "share_price"),
        }),
        ("وضعیت و نمایش", {
            "fields": ("status", "is_visible", "is_active"),
        }),
        ("مهلت زمانی", {
            "fields": ("has_deadline", "deadline"),
        }),
        ("شمارنده‌ها (خودکار)", {
            "fields": (
                "purchased_shares",
                "purchased_amount",
                "participant_count",
            ),
        }),
        ("Timeline", {
            "fields": (
                "published_at",
                "completed_at",
                "closed_at",
                "created_at",
                "updated_at",
            ),
        }),
    )

    @admin.display(description="پیشرفت")
    def progress_display(self, obj: Campaign) -> str:
        """نمایش گرافیکی درصد پیشرفت."""
        percent = obj.progress_percent
        color = "green" if percent >= 100 else "orange" if percent >= 50 else "red"
        return format_html(
            '<strong style="color: {};">{:.1f}%</strong>',
            color,
            percent,
        )


# ---------------------------------------------------------------------------
# CampaignImage
# ---------------------------------------------------------------------------

@admin.register(CampaignImage)
class CampaignImageAdmin(admin.ModelAdmin):
    """ادمین مستقل تصاویر گالری."""

    list_display = ("id", "campaign", "display_order", "is_active", "created_at")
    list_filter = ("is_active", "campaign")
    search_fields = ("campaign__title", "alt_text")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("campaign", "display_order")


# ---------------------------------------------------------------------------
# Participation
# ---------------------------------------------------------------------------

@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    """ادمین مشارکت‌ها — فقط خواندنی برای امنیت مالی."""

    list_display = (
        "id",
        "campaign",
        "user",
        "share_count",
        "total_amount",
        "status",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "campaign")
    search_fields = (
        "campaign__title",
        "user__email",
        "user__phone_number",
    )
    readonly_fields = (
        "campaign",
        "user",
        "share_count",
        "share_price_snapshot",
        "total_amount",
        "status",
        "paid_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """ایجاد مشارکت فقط از طریق API مجاز است."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """حذف مشارکت ممنوع — برای حفظ یکپارچگی مالی."""
        return False


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """ادمین پرداخت‌ها — فقط خواندنی."""

    list_display = (
        "id",
        "user",
        "amount",
        "gateway_name",
        "authority",
        "ref_id",
        "status",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "gateway_name")
    search_fields = ("authority", "ref_id", "user__email", "user__phone_number")
    readonly_fields = (
        "participation",
        "user",
        "amount",
        "gateway_name",
        "authority",
        "ref_id",
        "gateway_status",
        "status",
        "paid_at",
        "verified_at",
        "ip_address",
        "user_agent",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """ایجاد پرداخت فقط از طریق API/درگاه مجاز است."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """حذف پرداخت ممنوع — برای حفظ سوابق مالی."""
        return False
