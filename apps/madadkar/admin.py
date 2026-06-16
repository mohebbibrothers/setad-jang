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
    CampaignDisbursement,
    CampaignFinancialAdjustment,
    CampaignImage,
    DonationReceipt,
    MadadkarRiskSignal,
    Participation,
    Payment,
    PaymentEvent,
    PaymentReconciliationBatch,
    PaymentReconciliationItem,
    PaymentRefund,
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

    def has_change_permission(self, request, obj=None) -> bool:
        """ویرایش مشارکت ممنوع — برای حفظ یکپارچگی مالی."""
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

    def has_change_permission(self, request, obj=None) -> bool:
        """ویرایش پرداخت ممنوع — برای حفظ سوابق مالی."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """حذف پرداخت ممنوع — برای حفظ سوابق مالی."""
        return False


# ---------------------------------------------------------------------------
# PaymentEvent
# ---------------------------------------------------------------------------

@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    """ادمین ledger رویدادهای پرداخت — فقط خواندنی و append-only."""

    list_display = (
        "id",
        "payment",
        "event_kind",
        "previous_status",
        "new_status",
        "amount",
        "gateway_status",
        "created_at",
    )
    list_filter = ("event_kind", "previous_status", "new_status", "gateway_status")
    search_fields = ("payment__authority", "payment__ref_id", "ref_id")
    readonly_fields = (
        "payment",
        "event_kind",
        "previous_status",
        "new_status",
        "amount",
        "gateway_status",
        "ref_id",
        "metadata",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """ایجاد رویداد پرداخت فقط از service layer مجاز است."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """ویرایش رویداد پرداخت ممنوع است."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """حذف رویداد پرداخت ممنوع است."""
        return False


@admin.register(PaymentReconciliationBatch)
class PaymentReconciliationBatchAdmin(admin.ModelAdmin):
    """Admin inspection for payment reconciliation batches."""

    list_display = ("provider_name", "status", "total_rows", "matched_count", "mismatch_count", "created_at")
    list_filter = ("provider_name", "status")
    search_fields = ("provider_name", "source_name")
    readonly_fields = [field.name for field in PaymentReconciliationBatch._meta.fields]


@admin.register(PaymentReconciliationItem)
class PaymentReconciliationItemAdmin(admin.ModelAdmin):
    """Admin inspection for payment reconciliation items."""

    list_display = ("batch", "payment", "authority", "provider_ref_id", "provider_amount", "internal_amount", "status")
    list_filter = ("status", "batch__provider_name")
    search_fields = ("authority", "provider_ref_id", "payment__authority", "payment__ref_id")
    raw_id_fields = ("batch", "payment")
    readonly_fields = [field.name for field in PaymentReconciliationItem._meta.fields]


# ---------------------------------------------------------------------------
# Refund / financial adjustment controls
# ---------------------------------------------------------------------------

@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    """Read-oriented admin for refund workflow evidence."""

    list_display = ("id", "payment", "amount", "reason", "status", "requested_by", "reviewed_by", "created_at")
    list_filter = ("status", "reason")
    search_fields = ("payment__authority", "payment__ref_id", "provider_ref_id")
    readonly_fields = (
        "payment",
        "requested_by",
        "reviewed_by",
        "amount",
        "reason",
        "status",
        "idempotency_key",
        "provider_ref_id",
        "note",
        "rejection_reason",
        "reviewed_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Refunds must be created through audited service/API workflow."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Refund workflow mutation is restricted to audited API actions."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Refund evidence must not be deleted from admin."""
        return False


@admin.register(CampaignFinancialAdjustment)
class CampaignFinancialAdjustmentAdmin(admin.ModelAdmin):
    """Read-oriented admin for financial adjustment workflow evidence."""

    list_display = ("id", "campaign", "adjustment_type", "amount", "status", "requested_by", "reviewed_by", "created_at")
    list_filter = ("status", "adjustment_type")
    search_fields = ("campaign__title", "payment__authority", "reason")
    readonly_fields = (
        "campaign",
        "payment",
        "requested_by",
        "reviewed_by",
        "adjustment_type",
        "status",
        "amount",
        "reason",
        "note",
        "rejection_reason",
        "reviewed_at",
        "applied_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Adjustments must be created through audited service/API workflow."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Adjustment workflow mutation is restricted to audited API actions."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Adjustment evidence must not be deleted from admin."""
        return False


@admin.register(MadadkarRiskSignal)
class MadadkarRiskSignalAdmin(admin.ModelAdmin):
    """Read-oriented admin for Madadkar risk signals."""

    list_display = ("id", "signal_type", "severity", "status", "user", "campaign", "ip_address", "created_at")
    list_filter = ("signal_type", "severity", "status")
    search_fields = ("user__email", "campaign__title", "payment__authority", "ip_address")
    readonly_fields = (
        "signal_type",
        "severity",
        "status",
        "user",
        "campaign",
        "payment",
        "refund",
        "adjustment",
        "ip_address",
        "description",
        "metadata",
        "reviewed_by",
        "reviewed_at",
        "review_note",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Risk signals are generated by risk services, not manually in admin."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Risk review must use audited admin API workflow."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Risk evidence must remain available for forensic review."""
        return False


@admin.register(DonationReceipt)
class DonationReceiptAdmin(admin.ModelAdmin):
    """Read-oriented admin for verifiable donation receipts."""

    list_display = ("receipt_number", "user", "campaign", "amount", "issued_at", "resend_count")
    list_filter = ("campaign", "issued_at")
    search_fields = ("receipt_number", "receipt_hash", "payment__authority", "user__email")
    readonly_fields = (
        "payment",
        "user",
        "campaign",
        "receipt_number",
        "receipt_hash",
        "hash_version",
        "amount",
        "issued_at",
        "payment_snapshot",
        "campaign_snapshot",
        "donor_snapshot",
        "resend_count",
        "last_resent_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-issued_at",)

    def has_add_permission(self, request) -> bool:
        """Receipts are issued by payment services, not manually in admin."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Receipt payload is immutable; resend is handled by audited API."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Receipt evidence must remain available for verification."""
        return False


@admin.register(CampaignDisbursement)
class CampaignDisbursementAdmin(admin.ModelAdmin):
    """Read-oriented admin for campaign disbursement workflow evidence."""

    list_display = ("id", "campaign", "amount", "recipient_name", "status", "requested_by", "reviewed_by", "paid_by", "created_at")
    list_filter = ("status", "campaign")
    search_fields = ("campaign__title", "recipient_name", "recipient_identifier", "bank_tracking_reference")
    readonly_fields = [field.name for field in CampaignDisbursement._meta.fields]
    ordering = ("-created_at",)

    def has_add_permission(self, request) -> bool:
        """Disbursements must be requested through audited API workflow."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Disbursement transitions must use audited API actions."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Disbursement evidence must not be deleted."""
        return False
