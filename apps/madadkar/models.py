"""
مدل‌های اپ مددکار — مشارکت خیریه سهم‌محور.

ساختار:
- Sponsor: نهاد میزبان (بانی) حرکت‌ها.
- Campaign: یک طرح خیریه با مبلغ کل و تعداد سهم مشخص.
- CampaignImage: گالری تصاویر اضافی هر حرکت.
- Participation: یک خرید سهم توسط کاربر در یک حرکت.
- Payment: رکورد تراکنش مالی مرتبط با یک Participation.

اصول معماری:
- BaseModel: soft delete + timestamps + ActiveManager.
- Denormalized counters روی Campaign برای کاهش JOIN در queryهای عمومی.
- Concurrency safety در service layer با select_for_update.
- Slug مبتنی بر title/name برای URLهای خوانا.
- DB-level constraints برای جلوگیری از داده‌های inconsistent.
"""

from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.core.models import BaseModel
from apps.madadkar.choices import (
    CampaignStatus,
    DisbursementStatus,
    FinancialAdjustmentStatus,
    FinancialAdjustmentType,
    FinancialControlSeverity,
    MadadkarRiskSeverity,
    MadadkarRiskSignalType,
    MadadkarRiskStatus,
    ParticipationStatus,
    PaymentEventKind,
    PaymentStatus,
    ReconciliationItemStatus,
    ReconciliationStatus,
    RefundReason,
    RefundStatus,
)
from apps.madadkar.managers import (
    CampaignAcceptingSharesManager,
    CampaignVisibleManager,
)
from apps.madadkar.validators import (
    validate_image_extension,
    validate_image_size,
    validate_share_count,
    validate_total_amount,
    validate_total_shares,
)

# ---------------------------------------------------------------------------
# Upload path helpers
# ---------------------------------------------------------------------------


def sponsor_logo_upload_path(instance: Sponsor, filename: str) -> str:
    """مسیر آپلود لوگوی مددکار."""
    return f"madadkar/sponsors/{instance.pk or 'new'}/logo/{filename}"


def campaign_cover_upload_path(instance: Campaign, filename: str) -> str:
    """مسیر آپلود تصویر اصلی حرکت."""
    return f"madadkar/campaigns/{instance.pk or 'new'}/cover/{filename}"


def campaign_gallery_upload_path(instance: CampaignImage, filename: str) -> str:
    """مسیر آپلود تصاویر گالری حرکت."""
    return f"madadkar/campaigns/{instance.campaign_id}/gallery/{filename}"


# ---------------------------------------------------------------------------
# Sponsor (مددکار)
# ---------------------------------------------------------------------------


class Sponsor(BaseModel):
    """
    نهاد میزبان حرکت‌های خیریه.

    مثال: «گروه جهادی انصارالزهرا»، «بنیاد علوی».
    یک Sponsor می‌تواند چند Campaign داشته باشد (one-to-many).
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="نام مددکار",
    )
    slug = models.SlugField(
        max_length=220,
        unique=True,
        allow_unicode=True,
        blank=True,
        verbose_name="شناسه URL",
        help_text="در صورت خالی بودن، از روی نام به‌صورت خودکار ساخته می‌شود.",
    )
    logo = models.ImageField(
        upload_to=sponsor_logo_upload_path,
        blank=True,
        null=True,
        validators=[validate_image_extension, validate_image_size],
        verbose_name="لوگو",
    )

    class Meta:
        verbose_name = "مددکار"
        verbose_name_plural = "مددکاران"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["slug"], name="madadkar_sponsor_slug_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        """تولید خودکار slug در صورت خالی بودن."""
        if not self.slug:
            base = slugify(self.name, allow_unicode=True) or "sponsor"
            self.slug = base[:220]
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Campaign (حرکت)
# ---------------------------------------------------------------------------


class Campaign(BaseModel):
    """
    یک حرکت خیریه — هسته اصلی اپ مددکار.

    فلسفه:
    - ادمین مبلغ کل (total_amount) و تعداد سهم (total_shares) را مشخص می‌کند.
    - share_price = total_amount / total_shares (در lifecycle محاسبه می‌شود).
    - کاربران سهم خریداری می‌کنند → counterها در service بروز می‌شوند.

    Denormalized counters:
    - purchased_shares: مجموع سهم‌های PAID + PENDING_PAYMENT (یعنی رزرو شده).
    - purchased_amount: مجموع مبلغ سهم‌های PAID (فقط پرداخت قطعی).
    - participant_count: تعداد کاربران یکتای دارای حداقل یک Participation PAID.

    Lifecycle:
    DRAFT → PUBLISHED → COMPLETED (auto on 100%)
                     → CLOSED    (manual or deadline)

    Managers:
    - objects: همه رکوردهای is_active=True (از BaseModel).
    - all_objects: همه رکوردها حتی soft-deleted (از BaseModel).
    - visible: فقط حرکت‌های قابل نمایش عمومی.
    - accepting: فقط حرکت‌های PUBLISHED + visible (در حال پذیرش سهم).
    """

    # ── Relations
    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.PROTECT,
        related_name="campaigns",
        verbose_name="مددکار",
    )

    # ── Identity
    title = models.CharField(
        max_length=300,
        verbose_name="عنوان حرکت",
    )
    slug = models.SlugField(
        max_length=320,
        unique=True,
        allow_unicode=True,
        blank=True,
        verbose_name="شناسه URL",
        help_text="در صورت خالی بودن، از روی عنوان به‌صورت خودکار ساخته می‌شود.",
    )
    description = models.TextField(
        verbose_name="توضیحات",
    )

    # ── Cover image (تصویر اصلی، جدا از گالری)
    cover_image = models.ImageField(
        upload_to=campaign_cover_upload_path,
        validators=[validate_image_extension, validate_image_size],
        verbose_name="تصویر اصلی",
    )

    # ── Financial
    total_amount = models.PositiveBigIntegerField(
        validators=[validate_total_amount],
        verbose_name="مبلغ کل (تومان)",
    )
    total_shares = models.PositiveIntegerField(
        validators=[validate_total_shares],
        verbose_name="تعداد کل سهم",
    )
    share_price = models.PositiveBigIntegerField(
        verbose_name="قیمت هر سهم (تومان)",
        help_text="به‌صورت خودکار از total_amount / total_shares محاسبه می‌شود.",
    )

    # ── Denormalized counters (sync after each payment)
    purchased_shares = models.PositiveIntegerField(
        default=0,
        verbose_name="سهم‌های فروخته/رزرو شده",
        help_text="مجموع سهم‌های PAID + PENDING_PAYMENT.",
    )
    purchased_amount = models.PositiveBigIntegerField(
        default=0,
        verbose_name="مبلغ جمع‌آوری‌شده (تومان)",
        help_text="فقط مجموع مبلغ پرداخت‌های قطعی (PAID).",
    )
    participant_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد مشارکت‌کنندگان یکتا",
    )

    # ── Lifecycle
    status = models.CharField(
        max_length=20,
        choices=CampaignStatus.choices,
        default=CampaignStatus.DRAFT,
        db_index=True,
        verbose_name="وضعیت",
    )
    is_visible = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="قابل نمایش در سایت",
        help_text="در صورت غیرفعال بودن، حرکت در API عمومی نمایش داده نمی‌شود.",
    )
    has_deadline = models.BooleanField(
        default=False,
        verbose_name="دارای مهلت زمانی",
    )
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="مهلت پایان",
        help_text="فقط زمانی استفاده می‌شود که has_deadline=True باشد.",
    )

    # ── Timeline
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان انتشار",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان تکمیل (۱۰۰٪ فروش)",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان بسته شدن",
    )

    # ── Extra managers (objects + all_objects از BaseModel به ارث می‌رسند)
    visible = CampaignVisibleManager()
    accepting = CampaignAcceptingSharesManager()

    class Meta:
        verbose_name = "حرکت"
        verbose_name_plural = "حرکت‌ها"
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["slug"], name="madadkar_camp_slug_idx"),
            models.Index(
                fields=["status", "is_visible"],
                name="madadkar_camp_status_vis_idx",
            ),
            models.Index(
                fields=["sponsor", "status"],
                name="madadkar_camp_sponsor_idx",
            ),
            models.Index(fields=["deadline"], name="madadkar_camp_deadline_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=1000),
                name="madadkar_camp_total_amount_min",
            ),
            models.CheckConstraint(
                condition=models.Q(total_shares__gte=1),
                name="madadkar_camp_total_shares_min",
            ),
            models.CheckConstraint(
                condition=models.Q(share_price__gte=1),
                name="madadkar_camp_share_price_min",
            ),
            models.CheckConstraint(
                condition=models.Q(purchased_shares__lte=models.F("total_shares")),
                name="madadkar_camp_purchased_lte_total",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(has_deadline=False, deadline__isnull=True)
                    | models.Q(has_deadline=True, deadline__isnull=False)
                ),
                name="madadkar_camp_deadline_consistency",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def _build_unique_slug(self, *, source: str | None = None) -> str:
        """Build a deterministic unique slug, adding a numeric suffix if needed."""
        base = slugify(source or self.slug or self.title, allow_unicode=True) or "campaign"
        max_length = self._meta.get_field("slug").max_length
        candidate = base[:max_length]

        existing = Campaign.all_objects.filter(slug=candidate)
        if self.pk:
            existing = existing.exclude(pk=self.pk)
        if not existing.exists():
            return candidate

        for counter in range(2, 10_000):
            suffix = f"-{counter}"
            candidate = f"{base[: max_length - len(suffix)]}{suffix}"
            existing = Campaign.all_objects.filter(slug=candidate)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if not existing.exists():
                return candidate

        raise ValidationError("امکان ساخت شناسه URL یکتا برای این حرکت وجود ندارد.")

    def clean(self) -> None:
        """Validate and normalize auto-generated slug before DB constraints run."""
        super().clean()
        if not self.slug:
            self.slug = self._build_unique_slug(source=self.title)
            return

        duplicate = Campaign.all_objects.filter(slug=self.slug)
        if self.pk:
            duplicate = duplicate.exclude(pk=self.pk)
        if duplicate.exists():
            self.slug = self._build_unique_slug(source=self.slug)

    def save(self, *args, **kwargs) -> None:
        """
        محاسبه خودکار share_price و تولید slug یکتا.

        نکته: divisibility در validator/service چک می‌شود — اینجا فقط محاسبه است.
        """
        if not self.slug:
            self.slug = self._build_unique_slug(source=self.title)
        elif Campaign.all_objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
            self.slug = self._build_unique_slug(source=self.slug)

        if self.total_shares and self.total_amount:
            self.share_price = self.total_amount // self.total_shares

        super().save(*args, **kwargs)

    # ── Computed properties ────────────────────────────────────────────

    @property
    def remaining_shares(self) -> int:
        """تعداد سهم باقی‌مانده برای فروش."""
        return max(self.total_shares - self.purchased_shares, 0)

    @property
    def progress_percent(self) -> float:
        """درصد پیشرفت فروش (یک رقم اعشار)."""
        if self.total_shares <= 0:
            return 0.0
        return round((self.purchased_shares / self.total_shares) * 100, 1)

    @property
    def is_fully_funded(self) -> bool:
        """آیا تمام سهم‌ها رزرو/فروخته شده‌اند؟"""
        return self.purchased_shares >= self.total_shares


# ---------------------------------------------------------------------------
# CampaignImage (گالری تصاویر اضافی)
# ---------------------------------------------------------------------------


class CampaignImage(BaseModel):
    """
    تصاویر اضافی گالری یک حرکت (علاوه بر cover_image اصلی).

    نکته: تصویر اصلی روی خود Campaign ذخیره می‌شود (cover_image).
    این مدل فقط برای تصاویر مکمل گالری است.
    """

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="gallery_images",
        verbose_name="حرکت",
    )
    image = models.ImageField(
        upload_to=campaign_gallery_upload_path,
        validators=[validate_image_extension, validate_image_size],
        verbose_name="تصویر",
    )
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="متن جایگزین",
    )
    display_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="ترتیب نمایش",
    )

    class Meta:
        verbose_name = "تصویر گالری حرکت"
        verbose_name_plural = "تصاویر گالری حرکت‌ها"
        ordering = ["display_order", "created_at"]
        indexes = [
            models.Index(
                fields=["campaign", "display_order"],
                name="madadkar_img_camp_order_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Image #{self.pk} of campaign {self.campaign_id}"


# ---------------------------------------------------------------------------
# Participation (مشارکت)
# ---------------------------------------------------------------------------


class Participation(BaseModel):
    """
    یک مشارکت کاربر در یک حرکت (خرید n سهم).

    نکات حیاتی:
    - share_price_snapshot: قیمت سهم در لحظه ایجاد ذخیره می‌شود (immutable).
      حتی اگر ادمین بعداً قیمت سهم را تغییر دهد، این مقدار ثابت می‌ماند.
    - total_amount = share_count * share_price_snapshot (در service محاسبه).
    - share reservation: هنگام initiate شدن، سهم‌ها در Campaign رزرو می‌شوند.
      اگر پرداخت ناموفق یا expire شود، سهم‌ها در service آزاد می‌شوند.
    """

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="participations",
        verbose_name="حرکت",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="madadkar_participations",
        verbose_name="کاربر",
    )

    share_count = models.PositiveIntegerField(
        validators=[validate_share_count],
        verbose_name="تعداد سهم",
    )
    share_price_snapshot = models.PositiveBigIntegerField(
        verbose_name="قیمت سهم در لحظه خرید (تومان)",
    )
    total_amount = models.PositiveBigIntegerField(
        verbose_name="مبلغ کل (تومان)",
    )

    status = models.CharField(
        max_length=20,
        choices=ParticipationStatus.choices,
        default=ParticipationStatus.PENDING_PAYMENT,
        db_index=True,
        verbose_name="وضعیت",
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان پرداخت موفق",
    )

    class Meta:
        verbose_name = "مشارکت"
        verbose_name_plural = "مشارکت‌ها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["campaign", "status"],
                name="madadkar_part_camp_status_idx",
            ),
            models.Index(
                fields=["user", "status"],
                name="madadkar_part_user_status_idx",
            ),
            models.Index(
                fields=["status", "created_at"],
                name="madadkar_part_status_time_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(share_count__gte=1),
                name="madadkar_part_share_count_min",
            ),
            models.CheckConstraint(
                condition=models.Q(share_price_snapshot__gte=1),
                name="madadkar_part_price_snapshot_min",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=1),
                name="madadkar_part_total_amount_min",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Participation #{self.pk}: user={self.user_id} "
            f"campaign={self.campaign_id} shares={self.share_count}"
        )


# ---------------------------------------------------------------------------
# Payment (پرداخت)
# ---------------------------------------------------------------------------


class Payment(BaseModel):
    """
    تراکنش پرداخت متصل به یک Participation.

    نکات امنیتی:
    - authority: کد یکتایی که توسط درگاه پرداخت تولید می‌شود.
    - idempotent verify: اگر یک Payment قبلاً SUCCESS شده، verify دوباره
      تغییری ایجاد نمی‌کند (در service).
    - ip_address + user_agent برای ردیابی و audit ذخیره می‌شود.
    - amount در زمان verify با مقدار درگاه مقایسه می‌شود (anti-tampering).
    """

    participation = models.OneToOneField(
        Participation,
        on_delete=models.PROTECT,
        related_name="payment",
        verbose_name="مشارکت",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="madadkar_payments",
        verbose_name="کاربر",
        help_text="denormalized برای سرعت query (برابر participation.user).",
    )
    amount = models.PositiveBigIntegerField(
        verbose_name="مبلغ (تومان)",
    )

    # ── Gateway integration
    gateway_name = models.CharField(
        max_length=50,
        verbose_name="نام درگاه",
        help_text="مثال: sandbox, zarinpal, idpay",
    )
    authority = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name="کد رهگیری درگاه (authority)",
    )
    ref_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="شناسه مرجع پرداخت (ref_id)",
        help_text="پس از verify موفق توسط درگاه برگردانده می‌شود.",
    )
    gateway_status = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="کد وضعیت خام درگاه",
    )

    # ── Status
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
        verbose_name="وضعیت",
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان پرداخت",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان تأیید توسط درگاه",
    )

    # ── Audit / traceability
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="آدرس IP",
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="User Agent",
    )

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت‌ها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["authority"], name="madadkar_pay_auth_idx"),
            models.Index(
                fields=["status", "created_at"],
                name="madadkar_pay_status_time_idx",
            ),
            models.Index(
                fields=["user", "status"],
                name="madadkar_pay_user_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=1),
                name="madadkar_pay_amount_min",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Payment #{self.pk}: authority={self.authority} "
            f"status={self.status} amount={self.amount}"
        )


# ---------------------------------------------------------------------------
# PaymentEvent (ledger رویدادهای مالی)
# ---------------------------------------------------------------------------


class PaymentEventQuerySet(models.QuerySet):
    """QuerySet append-only برای جلوگیری از تغییر bulk در ledger پرداخت."""

    def update(self, **kwargs):
        """Bulk update روی ledger مالی ممنوع است."""
        raise PermissionError("ویرایش رویدادهای پرداخت مجاز نیست.")

    def delete(self):
        """Bulk delete روی ledger مالی ممنوع است."""
        raise PermissionError("حذف رویدادهای پرداخت مجاز نیست.")


class PaymentEventManager(models.Manager.from_queryset(PaymentEventQuerySet)):
    """Manager append-only برای PaymentEvent."""


class PaymentEvent(BaseModel):
    """
    Ledger append-only رویدادهای پرداخت.

    این مدل برای forensic/reconciliation مالی است و هر تغییر مهم در چرخه پرداخت
    را به‌صورت immutable ثبت می‌کند. Payment آخرین state را نگه می‌دارد؛
    PaymentEvent مسیر رسیدن به آن state را.
    """

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="events",
        verbose_name="پرداخت",
    )
    event_kind = models.CharField(
        max_length=30,
        choices=PaymentEventKind.choices,
        verbose_name="نوع رویداد",
    )
    previous_status = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="وضعیت قبلی",
    )
    new_status = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="وضعیت جدید",
    )
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ (تومان)")
    gateway_status = models.CharField(max_length=50, blank=True, verbose_name="وضعیت درگاه")
    ref_id = models.CharField(max_length=100, blank=True, verbose_name="شناسه مرجع")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="داده تکمیلی")

    objects = PaymentEventManager()
    all_objects = PaymentEventManager()

    class Meta:
        verbose_name = "رویداد پرداخت"
        verbose_name_plural = "رویدادهای پرداخت"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["payment", "event_kind"], name="madadkar_evt_payment_kind_idx"),
            models.Index(fields=["event_kind", "-created_at"], name="madadkar_evt_kind_time_idx"),
        ]

    def __str__(self) -> str:
        return f"PaymentEvent #{self.pk}: payment={self.payment_id} kind={self.event_kind}"

    def save(self, *args, **kwargs) -> None:
        """فقط insert مجاز است؛ update رویداد مالی ممنوع است."""
        if self.pk and not self._state.adding:
            raise PermissionError("ویرایش رویدادهای پرداخت مجاز نیست.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """حذف hard رویداد مالی ممنوع است."""
        raise PermissionError("حذف رویدادهای پرداخت مجاز نیست.")

    def soft_delete(self) -> None:
        """حذف نرم رویداد مالی ممنوع است."""
        raise PermissionError("حذف رویدادهای پرداخت مجاز نیست.")

    def restore(self) -> None:
        """بازیابی روی ledger append-only معنا ندارد."""
        raise PermissionError("بازیابی رویدادهای پرداخت مجاز نیست.")


# ---------------------------------------------------------------------------
# Refund / Adjustment Workflow
# ---------------------------------------------------------------------------


class PaymentRefund(BaseModel):
    """Controlled refund workflow for successful Madadkar payments."""

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name="پرداخت",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="madadkar_refunds_requested",
        verbose_name="درخواست‌کننده",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="madadkar_refunds_reviewed",
        verbose_name="بررسی‌کننده",
    )
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ بازپرداخت")
    reason = models.CharField(max_length=40, choices=RefundReason.choices, verbose_name="دلیل")
    status = models.CharField(
        max_length=30,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING_REVIEW,
        db_index=True,
        verbose_name="وضعیت",
    )
    idempotency_key = models.CharField(max_length=120, null=True, blank=True, unique=True)
    provider_ref_id = models.CharField(
        max_length=120, blank=True, verbose_name="شناسه بازپرداخت درگاه"
    )
    note = models.TextField(blank=True, verbose_name="یادداشت")
    rejection_reason = models.TextField(blank=True, verbose_name="دلیل رد")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "بازپرداخت مددکار"
        verbose_name_plural = "بازپرداخت‌های مددکار"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["payment", "status"], name="md_ref_pay_status_idx"),
            models.Index(fields=["status", "-created_at"], name="madadkar_ref_status_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=1), name="madadkar_ref_amount_min"
            ),
        ]

    def __str__(self) -> str:
        return f"Refund #{self.pk}: payment={self.payment_id} amount={self.amount} status={self.status}"

    @property
    def is_full_refund(self) -> bool:
        """Whether this refund covers the entire payment amount."""
        return self.amount >= self.payment.amount


class CampaignFinancialAdjustment(BaseModel):
    """Auditable manual financial adjustment for campaign accounting."""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="financial_adjustments",
        verbose_name="حرکت",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_adjustments",
        verbose_name="پرداخت مرتبط",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="madadkar_adjustments_requested",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="madadkar_adjustments_reviewed",
    )
    adjustment_type = models.CharField(max_length=20, choices=FinancialAdjustmentType.choices)
    status = models.CharField(
        max_length=30,
        choices=FinancialAdjustmentStatus.choices,
        default=FinancialAdjustmentStatus.PENDING_REVIEW,
        db_index=True,
    )
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ اصلاح")
    reason = models.CharField(max_length=240, verbose_name="دلیل")
    note = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "اصلاح مالی کمپین"
        verbose_name_plural = "اصلاحات مالی کمپین"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campaign", "status"], name="md_adj_camp_status_idx"),
            models.Index(fields=["status", "-created_at"], name="madadkar_adj_status_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=1), name="madadkar_adj_amount_min"
            ),
        ]

    def __str__(self) -> str:
        return f"Adjustment #{self.pk}: campaign={self.campaign_id} amount={self.amount} status={self.status}"

    @property
    def signed_amount(self) -> int:
        """Return positive credit or negative debit amount for reporting."""
        if self.adjustment_type == FinancialAdjustmentType.CREDIT:
            return self.amount
        return -self.amount


# ---------------------------------------------------------------------------
# Financial Control Snapshots
# ---------------------------------------------------------------------------


class MadadkarFinancialControlSnapshot(BaseModel):
    """Automated finance-ops control report for Madadkar operational safety."""

    generated_for_date = models.DateField(db_index=True)
    severity = models.CharField(
        max_length=20,
        choices=FinancialControlSeverity.choices,
        default=FinancialControlSeverity.HEALTHY,
        db_index=True,
    )
    summary = models.JSONField(default=dict, blank=True)
    controls = models.JSONField(default=dict, blank=True)
    flags = models.JSONField(default=list, blank=True)
    generated_by_task_id = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "Snapshot کنترل مالی مددکار"
        verbose_name_plural = "Snapshotهای کنترل مالی مددکار"
        ordering = ["-generated_for_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["generated_for_date", "severity"], name="madadkar_ctrl_date_sev_idx"
            ),
            models.Index(fields=["severity", "-created_at"], name="madadkar_ctrl_sev_time_idx"),
        ]

    def __str__(self) -> str:
        return f"MadadkarFinancialControlSnapshot {self.generated_for_date}:{self.severity}"


# ---------------------------------------------------------------------------
# Disbursement / Allocation Ledger
# ---------------------------------------------------------------------------


class CampaignDisbursement(BaseModel):
    """Auditable workflow for allocating collected campaign funds to recipients."""

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="disbursements",
        verbose_name="حرکت",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="madadkar_disbursements_requested",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="madadkar_disbursements_reviewed",
    )
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="madadkar_disbursements_paid",
    )
    status = models.CharField(
        max_length=20,
        choices=DisbursementStatus.choices,
        default=DisbursementStatus.REQUESTED,
        db_index=True,
    )
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ تخصیص")
    recipient_name = models.CharField(max_length=220, verbose_name="نام گیرنده")
    recipient_identifier = models.CharField(
        max_length=120, blank=True, verbose_name="شناسه/کد گیرنده"
    )
    recipient_bank_account = models.CharField(
        max_length=120, blank=True, verbose_name="حساب/شبا مقصد"
    )
    recipient_snapshot = models.JSONField(default=dict, blank=True)
    purpose = models.CharField(max_length=260, verbose_name="هدف تخصیص")
    note = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    bank_tracking_reference = models.CharField(max_length=120, blank=True)
    supporting_document = models.JSONField(default=dict, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "تخصیص مالی مددکار"
        verbose_name_plural = "تخصیص‌های مالی مددکار"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["campaign", "status", "-created_at"], name="md_disb_camp_status_idx"
            ),
            models.Index(fields=["status", "-created_at"], name="madadkar_disb_status_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=1), name="madadkar_disb_amount_min"
            ),
        ]

    def __str__(self) -> str:
        return f"Disbursement #{self.pk}: campaign={self.campaign_id} amount={self.amount} status={self.status}"


# ---------------------------------------------------------------------------
# Donation Receipts
# ---------------------------------------------------------------------------


class DonationReceipt(BaseModel):
    """Verifiable donation receipt issued for a successful Madadkar payment."""

    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="donation_receipt",
        verbose_name="پرداخت",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="madadkar_donation_receipts",
        verbose_name="کاربر",
    )
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name="donation_receipts",
        verbose_name="حرکت",
    )
    receipt_number = models.CharField(max_length=40, unique=True, db_index=True)
    receipt_hash = models.CharField(max_length=64, unique=True, db_index=True)
    hash_version = models.PositiveSmallIntegerField(default=1)
    amount = models.PositiveBigIntegerField(verbose_name="مبلغ رسید")
    issued_at = models.DateTimeField(verbose_name="زمان صدور")
    payment_snapshot = models.JSONField(default=dict, blank=True)
    campaign_snapshot = models.JSONField(default=dict, blank=True)
    donor_snapshot = models.JSONField(default=dict, blank=True)
    resend_count = models.PositiveIntegerField(default=0)
    last_resent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "رسید مشارکت مددکار"
        verbose_name_plural = "رسیدهای مشارکت مددکار"
        ordering = ["-issued_at", "-created_at"]
        indexes = [
            models.Index(fields=["user", "-issued_at"], name="madadkar_receipt_user_time_idx"),
            models.Index(fields=["campaign", "-issued_at"], name="md_receipt_camp_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=1), name="madadkar_receipt_amount_min"
            ),
        ]

    def __str__(self) -> str:
        return f"Receipt {self.receipt_number} payment={self.payment_id}"

    def build_hash_payload(self) -> dict:
        """Build deterministic payload used for public receipt verification."""
        return {
            "hash_version": self.hash_version,
            "receipt_number": self.receipt_number,
            "payment_id": self.payment_id,
            "user_id": self.user_id,
            "campaign_id": self.campaign_id,
            "amount": self.amount,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "payment_snapshot": self.payment_snapshot,
            "campaign_snapshot": self.campaign_snapshot,
            "donor_snapshot": self.donor_snapshot,
        }

    def compute_receipt_hash(self) -> str:
        """Compute deterministic SHA-256 hash for receipt verification."""
        encoded = json.dumps(
            self.build_hash_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def save(self, *args, **kwargs) -> None:
        """Fill receipt hash on insert and keep receipt evidence stable afterwards."""
        if self.pk and not self._state.adding:
            allowed_update_fields = set(kwargs.get("update_fields") or [])
            mutable_fields = {"resend_count", "last_resent_at", "updated_at"}
            if allowed_update_fields and allowed_update_fields.issubset(mutable_fields):
                super().save(*args, **kwargs)
                return
            raise PermissionError("ویرایش رسید مشارکت مجاز نیست.")
        if not self.receipt_hash:
            self.receipt_hash = self.compute_receipt_hash()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Risk Signals
# ---------------------------------------------------------------------------


class MadadkarRiskSignal(BaseModel):
    """Financial risk/abuse signal generated from Madadkar behavior."""

    signal_type = models.CharField(
        max_length=60, choices=MadadkarRiskSignalType.choices, db_index=True
    )
    severity = models.CharField(
        max_length=20,
        choices=MadadkarRiskSeverity.choices,
        default=MadadkarRiskSeverity.MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=MadadkarRiskStatus.choices,
        default=MadadkarRiskStatus.OPEN,
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="madadkar_risk_signals",
    )
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="risk_signals",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_signals",
    )
    refund = models.ForeignKey(
        PaymentRefund,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_signals",
    )
    adjustment = models.ForeignKey(
        CampaignFinancialAdjustment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_signals",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="madadkar_reviewed_risk_signals",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        verbose_name = "سیگنال ریسک مددکار"
        verbose_name_plural = "سیگنال‌های ریسک مددکار"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["signal_type", "status", "-created_at"],
                name="madadkar_risk_type_status_idx",
            ),
            models.Index(
                fields=["severity", "status", "-created_at"], name="madadkar_risk_sev_status_idx"
            ),
            models.Index(
                fields=["user", "status", "-created_at"], name="madadkar_risk_user_status_idx"
            ),
            models.Index(
                fields=["campaign", "status", "-created_at"], name="md_risk_camp_status_idx"
            ),
            models.Index(
                fields=["ip_address", "status", "-created_at"], name="madadkar_risk_ip_status_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.signal_type}:{self.severity}:{self.status}"


# ---------------------------------------------------------------------------
# Payment Reconciliation
# ---------------------------------------------------------------------------


class PaymentReconciliationBatch(BaseModel):
    """Batch report comparing external provider rows with internal payments."""

    provider_name = models.CharField(max_length=50, verbose_name="نام درگاه")
    source_name = models.CharField(max_length=180, blank=True, verbose_name="نام فایل/گزارش")
    status = models.CharField(
        max_length=20, choices=ReconciliationStatus.choices, default=ReconciliationStatus.DRAFT
    )
    total_rows = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    mismatch_count = models.PositiveIntegerField(default=0)
    missing_internal_count = models.PositiveIntegerField(default=0)
    duplicate_provider_ref_count = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Batch تطبیق پرداخت"
        verbose_name_plural = "Batchهای تطبیق پرداخت"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["provider_name", "status", "-created_at"])]

    def __str__(self) -> str:
        return f"Reconciliation {self.provider_name} #{self.pk}"


class PaymentReconciliationItem(BaseModel):
    """One provider row reconciliation result."""

    batch = models.ForeignKey(
        PaymentReconciliationBatch, on_delete=models.CASCADE, related_name="items"
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciliation_items",
    )
    authority = models.CharField(max_length=100, blank=True)
    provider_ref_id = models.CharField(max_length=100, blank=True)
    provider_amount = models.PositiveBigIntegerField(default=0)
    provider_status = models.CharField(max_length=50, blank=True)
    internal_amount = models.PositiveBigIntegerField(null=True, blank=True)
    internal_status = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=40, choices=ReconciliationItemStatus.choices)
    reason = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "ردیف تطبیق پرداخت"
        verbose_name_plural = "ردیف‌های تطبیق پرداخت"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["batch", "status"]),
            models.Index(fields=["authority"]),
            models.Index(fields=["provider_ref_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.batch_id}:{self.status}:{self.authority or self.provider_ref_id}"
