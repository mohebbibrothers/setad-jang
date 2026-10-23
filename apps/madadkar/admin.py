"""
Django Admin اپ مددکار.

تنظیمات admin برای مدیریت داخلی توسط superuserها.
نکته: عملیات حساس (مثل publish/close) از طریق API انجام می‌شود — admin فقط
برای CRUD ساده و debug است.
"""

from __future__ import annotations

import logging

from django import forms as forms_mod
from django.contrib import admin, messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django.utils.html import format_html

from apps.madadkar import services as madadkar_services
from apps.madadkar.forms import ExternalFundingAddForm, ExternalFundingInlineForm
from apps.madadkar.models import (
    Campaign,
    CampaignDisbursement,
    CampaignFinancialAdjustment,
    CampaignImage,
    DonationReceipt,
    ExternalFunding,
    MadadkarFinancialControlSnapshot,
    MadadkarRiskSignal,
    Participation,
    Payment,
    PaymentEvent,
    PaymentReconciliationBatch,
    PaymentReconciliationItem,
    PaymentRefund,
    Sponsor,
)

logger = logging.getLogger("apps.madadkar.admin")


class HiddenFromAdminIndexMixin:
    """Keep specialized/inline-only ModelAdmins registered but hidden from admin index."""

    def get_model_perms(self, request) -> dict[str, bool]:
        """Return no permissions so Django omits this model from the admin index."""
        return {}


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


class ExternalFundingInline(admin.TabularInline):
    """اینلاینِ «تأمین خارج از سایت» روی صفحه‌ی حرکت.

    قوانین ممیزی (عمدی):
    - فقط «افزودن» — رکوردهای ثبت‌شده از این‌جا ویرایش/حذف نمی‌شوند؛
      اشتباه‌ها با اکشنِ «ابطال» در ادمینِ مستقلِ ExternalFunding جبران
      می‌شوند تا سندِ مالی همیشه بماند.
    - ذخیره حتماً از سرویس عبور می‌کند (قفل + سقف + sync شمارنده‌ها)؛
      هر تلاشِ ویرایشی روی رکوردهای موجود با خطای پنل نادیده گرفته می‌شود.
    """

    model = ExternalFunding
    form = ExternalFundingInlineForm
    extra = 0
    fields = (
        "shares",
        "amount",
        "method",
        "reference",
        "funded_at",
        "note",
        "status_badge",
        "recorded_by",
        "created_at",
    )
    readonly_fields = ("status_badge", "recorded_by", "created_at")
    verbose_name = "تأمین خارج از سایت"
    verbose_name_plural = "تأمین‌های خارج از سایت (پویش آفلاین)"

    def get_formset(self, request, obj=None, **kwargs):
        """تزریق کمپین والد + راهنمای زنده‌ی سقف روی ردیف‌ها.

        obj همان Campaign است؛ راهنما عین آنچه ادمین لازم دارد می‌گوید:
        «چقدر می‌توانیم ثبت کنیم؟» — بدون ابهام.
        """
        formset = super().get_formset(request, obj, **kwargs)
        formset.form._campaign = obj
        if obj is not None:
            base = formset.form.base_fields["shares"]
            base.help_text = (
                f"باقی‌مانده‌ی قابل ثبت: {obj.remaining_shares:,} سهم "
                "(برای تأمین کامل از بیرون، همین عدد)"
            )
            base.widget = forms_mod.NumberInput(
                attrs={
                    "min": 1,
                    "max": obj.remaining_shares,
                    "placeholder": f"حداکثر {obj.remaining_shares:,}",
                }
            )
        return formset

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    @admin.display(description="وضعیت")
    def status_badge(self, obj: ExternalFunding) -> str:
        if obj is None or obj.pk is None:
            return "—"
        color = "#15803d" if obj.status == "recorded" else "#9ca3af"
        return format_html(
            '<b style="color:{}">{}</b>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="ثبت‌کننده")
    def recorded_by(self, obj: ExternalFunding) -> str:
        if obj is None or obj.pk is None:
            return "—"
        return str(obj.recorded_by) if obj.recorded_by else "—"


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
        "external_funded_shares",
        "total_shares",
        "offline_funding_link",
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
        "external_funded_shares",
        "external_funded_amount",
        "published_at",
        "completed_at",
        "closed_at",
        "created_at",
        "updated_at",
    )
    inlines = [CampaignImageInline, ExternalFundingInline]
    ordering = ("-created_at",)

    def save_formset(self, request, form, formset, change):
        """دروازه‌ی امن ذخیره‌ی اینلاین‌ها.

        ExternalFunding فقط از مسیر سرویس ساخته می‌شود (قفل + سقف سهم +
        sync شمارنده + تکمیل خودکار). ویرایش/حذف رکوردهای موجود از این‌جا
        ممنوع است — ابطال از ادمینِ مستقل انجام می‌شود.
        """
        if formset.model is ExternalFunding:
            instances = formset.save(commit=False)
            for instance in instances:
                if instance.pk is None:
                    try:
                        madadkar_services.record_external_funding(
                            campaign=instance.campaign,
                            shares=instance.shares,
                            amount=instance.amount,
                            method=instance.method,
                            reference=instance.reference,
                            note=instance.note,
                            funded_at=instance.funded_at,
                            recorded_by=request.user,
                        )
                    except DjangoValidationError as exc:
                        messages.error(request, f"ثبت تأمین خارجی انجام نشد: {exc.message}")
                    except Exception:
                        logger.exception("External funding record failed via campaign inline")
                        messages.error(
                            request,
                            "خطای غیرمنتظره هنگام ثبت تأمین خارجی رخ داد؛ جزئیات در لاگ ثبت شد.",
                        )
                else:
                    messages.warning(
                        request,
                        "ویرایش رکورد تأمین خارجی نادیده گرفته شد؛ برای اصلاح، "
                        "رکورد را از ادمین مستقل ابطال و رکورد تازه ثبت کنید.",
                    )
            formset.save_m2m()
            return
        super().save_formset(request, form, formset, change)

    fieldsets = (
        (
            "اطلاعات اصلی",
            {
                "fields": ("sponsor", "title", "slug", "description", "cover_image"),
            },
        ),
        (
            "مالی",
            {
                "fields": ("total_amount", "total_shares", "share_price"),
            },
        ),
        (
            "وضعیت و نمایش",
            {
                "fields": ("status", "is_visible", "is_active"),
            },
        ),
        (
            "مهلت زمانی",
            {
                "fields": ("has_deadline", "deadline"),
            },
        ),
        (
            "شمارنده‌ها (خودکار)",
            {
                "fields": (
                    "purchased_shares",
                    "purchased_amount",
                    "participant_count",
                    "external_funded_shares",
                    "external_funded_amount",
                ),
            },
        ),
        (
            "Timeline",
            {
                "fields": (
                    "published_at",
                    "completed_at",
                    "closed_at",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description="پیشرفت")
    def progress_display(self, obj: Campaign) -> str:
        """نمایش گرافیکی درصد پیشرفت."""
        percent = obj.progress_percent
        color = "green" if percent >= 100 else "orange" if percent >= 50 else "red"
        return format_html(
            '<strong style="color: {};">{}%</strong>',
            color,
            f"{percent:.1f}",
        )

    @admin.display(description="تأمین خارجی")
    def offline_funding_link(self, obj: Campaign) -> str:
        """دکمه‌ی مستقیم ثبت تأمین خارجی برای همین حرکت (پیش‌انتخاب‌شده)."""
        url = reverse("admin:madadkar_externalfunding_add") + f"?campaign={obj.pk}"
        return format_html(
            '<a class="button" href="{}" '
            'style="background:#417690;color:#fff;white-space:nowrap;">'
            "+ ثبت تأمین خارجی</a>",
            url,
        )


# ---------------------------------------------------------------------------
# CampaignImage
# ---------------------------------------------------------------------------


@admin.register(CampaignImage)
class CampaignImageAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
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
# PaymentEvent inline
# ---------------------------------------------------------------------------


class PaymentEventInline(admin.TabularInline):
    """Read-only payment event ledger embedded in the Payment workspace."""

    model = PaymentEvent
    extra = 0
    can_delete = False
    fields = (
        "event_kind",
        "previous_status",
        "new_status",
        "amount",
        "gateway_status",
        "ref_id",
        "created_at",
    )
    readonly_fields = fields
    ordering = ("-created_at",)
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:
        """Payment events are generated by the payment service layer."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Payment events are immutable ledger records."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Payment events must remain available for forensic review."""
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
    inlines = [PaymentEventInline]

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
class PaymentEventAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
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


class PaymentReconciliationItemInline(admin.TabularInline):
    """Read-only reconciliation rows embedded in the batch workspace."""

    model = PaymentReconciliationItem
    extra = 0
    can_delete = False
    fields = (
        "payment",
        "authority",
        "provider_ref_id",
        "provider_amount",
        "provider_status",
        "internal_amount",
        "internal_status",
        "status",
        "reason",
        "created_at",
    )
    readonly_fields = fields
    raw_id_fields = ("payment",)
    ordering = ("created_at", "id")
    show_change_link = True

    def has_add_permission(self, request, obj=None) -> bool:
        """Reconciliation rows are produced by the import service."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Reconciliation rows are immutable comparison evidence."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Reconciliation evidence must not be deleted from admin."""
        return False


@admin.register(PaymentReconciliationBatch)
class PaymentReconciliationBatchAdmin(admin.ModelAdmin):
    """Admin inspection for payment reconciliation batches."""

    list_display = (
        "provider_name",
        "status",
        "total_rows",
        "matched_count",
        "mismatch_count",
        "created_at",
    )
    list_filter = ("provider_name", "status")
    search_fields = ("provider_name", "source_name")
    readonly_fields = [field.name for field in PaymentReconciliationBatch._meta.fields]
    inlines = [PaymentReconciliationItemInline]
    ordering = ("-created_at",)


@admin.register(PaymentReconciliationItem)
class PaymentReconciliationItemAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    """Admin inspection for payment reconciliation items."""

    list_display = (
        "batch",
        "payment",
        "authority",
        "provider_ref_id",
        "provider_amount",
        "internal_amount",
        "status",
    )
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

    list_display = (
        "id",
        "payment",
        "amount",
        "reason",
        "status",
        "requested_by",
        "reviewed_by",
        "created_at",
    )
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

    list_display = (
        "id",
        "campaign",
        "adjustment_type",
        "amount",
        "status",
        "requested_by",
        "reviewed_by",
        "created_at",
    )
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

    list_display = (
        "id",
        "signal_type",
        "severity",
        "status",
        "user",
        "campaign",
        "ip_address",
        "created_at",
    )
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

    list_display = (
        "id",
        "campaign",
        "amount",
        "recipient_name",
        "status",
        "requested_by",
        "reviewed_by",
        "paid_by",
        "created_at",
    )
    list_filter = ("status", "campaign")
    search_fields = (
        "campaign__title",
        "recipient_name",
        "recipient_identifier",
        "bank_tracking_reference",
    )
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


@admin.register(MadadkarFinancialControlSnapshot)
class MadadkarFinancialControlSnapshotAdmin(admin.ModelAdmin):
    """Read-oriented admin for automated financial control snapshots."""

    list_display = ("id", "generated_for_date", "severity", "generated_by_task_id", "created_at")
    list_filter = ("severity", "generated_for_date")
    search_fields = ("generated_by_task_id",)
    readonly_fields = [field.name for field in MadadkarFinancialControlSnapshot._meta.fields]
    ordering = ("-generated_for_date", "-created_at")

    def has_add_permission(self, request) -> bool:
        """Snapshots are generated by audited API/task workflows."""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """Financial control evidence is immutable in admin."""
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        """Financial control evidence must remain available for review."""
        return False


# ---------------------------------------------------------------------------
# ExternalFunding (تأمین خارج از سایت — پویش آفلاین)
# ---------------------------------------------------------------------------


@admin.register(ExternalFunding)
class ExternalFundingAdmin(admin.ModelAdmin):
    """دفتر حسابرسیِ تأمین‌های خارج از سایت.

    - افزودن فقط از مسیر سرویس (قفل + سقف سهم + sync + تکمیل خودکار)
    - رکوردهای ثبت‌شده read-only‌اند؛ اصلاح = ابطال + ثبتِ تازه
    - حذفِ فیزیکی ممنوع — سند مالی حذف نمی‌شود
    """

    list_display = (
        "campaign",
        "shares",
        "amount",
        "method",
        "status",
        "funded_at",
        "recorded_by",
        "created_at",
    )
    list_filter = ("status", "method", "campaign__sponsor")
    search_fields = ("campaign__title", "reference", "note")
    date_hierarchy = "funded_at"
    ordering = ("-created_at",)
    actions = ("void_selected",)

    add_form = ExternalFundingAddForm
    _change_readonly = (
        "campaign",
        "shares",
        "amount",
        "share_price_snapshot",
        "method",
        "reference",
        "funded_at",
        "note",
        "status",
        "recorded_by",
        "void_reason",
        "voided_at",
        "created_at",
        "updated_at",
    )

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, **kwargs)

    def get_changeform_initial_data(self, request):
        """پیش‌انتخاب حرکت از لینکِ مستقیمِ لیست («+ ثبت تأمین خارجی»)."""
        initial = super().get_changeform_initial_data(request)
        if request.GET.get("campaign"):
            initial["campaign"] = request.GET["campaign"]
        return initial

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self._change_readonly

    def save_model(self, request, obj, form, change):
        """افزودن حتماً از سرویس عبور می‌کند تا atom/قفل/sync حفظ شود.

        ضد-۵۰۰: هر خطای غیرمنتظره به پیامِ پنل تبدیل می‌شود؛ صفحه‌ی ۵۰۰
        در این مسیر دیگر وجود نخواهد داشت.
        """
        if change:
            return  # صفحه‌ی تغییر fully-readonly است؛ کاری نمی‌ماند
        try:
            created = madadkar_services.record_external_funding(
                campaign=obj.campaign,
                shares=obj.shares,
                amount=obj.amount,
                method=obj.method,
                reference=obj.reference,
                note=obj.note,
                funded_at=obj.funded_at,
                recorded_by=request.user,
            )
        except DjangoValidationError as exc:
            # نبریُ race: فرم قبلاً سقف را چک کرده؛ اگر هم‌زمان سهم خورده
            # شده باشد، سرویس این‌جا دقیق جواب می‌دهد.
            messages.error(request, f"ثبت تأمین خارجی انجام نشد: {exc.message}")
            return
        except Exception:
            logger.exception("External funding record failed via admin form")
            messages.error(
                request,
                "خطای غیرمنتظره هنگام ثبت تأمین خارجی رخ داد؛ جزئیات در لاگ ثبت شد.",
            )
            return
        else:
            # pk رکوردِ واقعیِ ساخته‌شده توسط سرویس را به obj می‌چسبانیم تا
            # LogEntry ادمین به سندِ درست لینک شود.
            obj.pk = created.pk
            messages.success(
                request,
                f"تأمین خارجی ثبت شد ({created.shares:,} سهم) — شمارنده‌های حرکت فوراً به‌روزرسانی شدند.",
            )

    @admin.action(description="باطل‌کردن رکوردهای انتخابی (storno)")
    def void_selected(self, request, queryset):
        ok = 0
        for funding in queryset:
            try:
                madadkar_services.void_external_funding(
                    funding=funding,
                    reason=f"ابطال از پنل ادمین توسط {request.user}",
                )
                ok += 1
            except DjangoValidationError as exc:
                messages.warning(request, f"رکورد {funding.pk}: {exc.message}")
        if ok:
            messages.success(
                request,
                f"{ok} رکورد تأمین خارجی باطل شد و شمارنده‌ها اصلاح شدند.",
            )

    def has_delete_permission(self, request, obj=None) -> bool:
        """سند مالی هرگز حذف فیزیکی نمی‌شود؛ فقط ابطال."""
        return False
