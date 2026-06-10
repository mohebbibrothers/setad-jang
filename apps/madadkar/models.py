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

from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.core.models import BaseModel
from apps.madadkar.choices import (
    CampaignStatus,
    ParticipationStatus,
    PaymentEventKind,
    PaymentStatus,
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

    def save(self, *args, **kwargs) -> None:
        """
        محاسبه خودکار share_price و تولید slug.

        نکته: divisibility در validator/service چک می‌شود — اینجا فقط محاسبه است.
        """
        if not self.slug:
            base = slugify(self.title, allow_unicode=True) or "campaign"
            self.slug = base[:320]

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
