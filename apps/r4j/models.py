"""
Models اپ R4J — Reward for Justice.

این فایل تمام مدل‌های دامنه R4J را نگه می‌دارد:

- R4JCriminal              : پروفایل اصلی مجرم
- R4JCriminalAlias         : اسامی مستعار (relational برای search سریع)
- R4JCriminalPhone         : شماره‌های تماس مجرم
- R4JCriminalSocial        : حساب‌های شبکه‌های اجتماعی مجرم
- R4JCriminalPhoto         : عکس‌های مجرم — یکی به‌عنوان primary
- R4JCriminalAttachment    : اسناد و فایل‌های پشتیبان
- R4JCriminalFieldVisibility: کنترل نمایش فیلدها به public per-criminal
- R4JReport                : گزارش community برای تکمیل/اصلاح اطلاعات
- R4JReportFieldChange     : پیشنهاد تغییر برای یک فیلد خاص
- R4JReportAttachment      : فایل‌های ضمیمه به یک گزارش
- R4JBounty                : جایزه‌ی declarative یک کاربر برای یک مجرم

اصول طراحی:
- تمام مدل‌ها از BaseModel ارث‌بری می‌کنند (is_active, created_at, updated_at).
- soft delete پشتیبانی می‌شود ولی AuditLog-like immutability برای bountyها لازم نیست.
- ID-based یا slug-based lookups پشتیبانی می‌شود (slug + id hybrid).
- counters denormalized (total_bounty_amount / bounties_count) برای performance.
- بدون N+1 در selectorهای آینده.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import BaseModel

from .choices import (
    BountyStatus,
    CriminalAttachmentKind,
    EvidenceCustodyEventType,
    Gender,
    ReportFieldChangeStatus,
    ReportStatus,
    SocialPlatform,
)
from .managers import R4JCriminalActiveManager, R4JCriminalPublishedManager
from .validators import (
    R4J_BOUNTY_MIN_TOMAN,
    validate_attachment_size,
    validate_iranian_national_code,
    validate_phone_number,
    validate_photo_extension,
    validate_photo_size,
)

# ============================================================
# Upload paths
# ============================================================


def _criminal_photo_upload_path(instance: R4JCriminalPhoto, filename: str) -> str:
    """Internal helper for models."""
    return f"r4j/criminals/{instance.criminal_id}/photos/{filename}"


def _criminal_attachment_upload_path(
    instance: R4JCriminalAttachment, filename: str,
) -> str:
    """Internal helper for models."""
    return f"r4j/criminals/{instance.criminal_id}/attachments/{filename}"


def _report_attachment_upload_path(
    instance: R4JReportAttachment, filename: str,
) -> str:
    """Internal helper for models."""
    return f"r4j/reports/{instance.report_id}/attachments/{filename}"


# ============================================================
# R4JCriminal
# ============================================================


class R4JCriminal(BaseModel):
    """
    پروفایل اصلی یک مجرم.

    State machine:
    - draft (is_published=False) -> published (is_published=True)
    - active (is_active=True) -> soft-deleted (is_active=False)

    Denormalized counters:
    - total_bounty_toman: مجموع bountyهای active
    - bounties_count: تعداد bountyهای active
    این فیلدها در service layer هنگام تغییر bounty sync می‌شوند.
    """

    # ---- Identity ----
    first_name = models.CharField(max_length=150, verbose_name="نام")
    last_name = models.CharField(max_length=150, verbose_name="نام خانوادگی")
    slug = models.SlugField(
        max_length=200,
        unique=True,
        blank=True,
        verbose_name="شناسه URL",
        help_text="در صورت خالی بودن، خودکار از نام ساخته می‌شود.",
    )
    national_code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        validators=[validate_iranian_national_code],
        verbose_name="کد ملی",
        help_text="برای مجرمین غیرایرانی خالی می‌ماند.",
    )
    birth_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="تاریخ تولد",
    )
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        default=Gender.UNKNOWN,
        verbose_name="جنسیت",
    )

    # ---- Location ----
    country = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="کشور",
    )
    province = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="استان",
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="شهر",
    )

    # ---- Description ----
    description = models.TextField(
        blank=True,
        verbose_name="توضیحات",
    )
    crimes_summary = models.TextField(
        blank=True,
        verbose_name="خلاصه جرائم",
    )
    other_info = models.TextField(
        blank=True,
        verbose_name="سایر اطلاعات",
        help_text="متن آزاد برای ثبت هر اطلاعات تکمیلی.",
    )

    # ---- Publishing ----
    is_published = models.BooleanField(
        default=False,
        verbose_name="منتشر شده",
    )
    published_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="زمان انتشار",
    )

    # ---- Ownership ----
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="r4j_created_criminals",
        verbose_name="ثبت‌کننده",
    )

    # ---- Denormalized counters ----
    total_bounty_toman = models.BigIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="مجموع جوایز (تومان)",
    )
    bounties_count = models.PositiveIntegerField(
        default=0,
        verbose_name="تعداد جوایز",
    )

    # ---- Managers ----
    objects = R4JCriminalActiveManager()
    all_objects = models.Manager()
    published = R4JCriminalPublishedManager()

    class Meta:
        verbose_name = "مجرم"
        verbose_name_plural = "مجرمین"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_published", "is_active", "-created_at"]),
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["country", "province", "city"]),
            models.Index(fields=["gender", "is_published", "is_active"]),
            models.Index(fields=["-total_bounty_toman"]),
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or f"criminal#{self.pk}"

    # ---- Behavior ----

    def save(self, *args: object, **kwargs: object) -> None:
        """ساخت slug خودکار با مدیریت collision."""
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self) -> str:
        base = slugify(f"{self.first_name} {self.last_name}", allow_unicode=True)
        if not base:
            base = "criminal"

        candidate = base
        suffix = 2
        # collision-safe
        while R4JCriminal.all_objects.filter(slug=candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def publish(self) -> None:
        """انتشار پروفایل (idempotent)."""
        if self.is_published:
            return
        self.is_published = True
        self.published_at = timezone.now()
        self.save(update_fields=["is_published", "published_at", "updated_at"])

    def unpublish(self) -> None:
        """خروج از انتشار (idempotent)."""
        if not self.is_published:
            return
        self.is_published = False
        self.save(update_fields=["is_published", "updated_at"])

    def soft_delete(self) -> None:
        """soft delete + unpublish خودکار."""
        self.is_active = False
        self.is_published = False
        self.save(update_fields=["is_active", "is_published", "updated_at"])


# ============================================================
# R4JCriminalAlias
# ============================================================


class R4JCriminalAlias(BaseModel):
    """اسم مستعار یک مجرم — برای search سریع."""

    criminal = models.ForeignKey(
        R4JCriminal,
        on_delete=models.CASCADE,
        related_name="aliases",
        verbose_name="مجرم",
    )
    alias = models.CharField(max_length=200, verbose_name="نام مستعار")

    class Meta:
        verbose_name = "نام مستعار"
        verbose_name_plural = "نام‌های مستعار"
        ordering = ["alias"]
        indexes = [models.Index(fields=["alias"])]
        constraints = [
            models.UniqueConstraint(
                fields=["criminal", "alias"],
                name="uniq_r4j_alias_per_criminal",
            ),
        ]

    def __str__(self) -> str:
        return self.alias


# ============================================================
# R4JCriminalPhone
# ============================================================


class R4JCriminalPhone(BaseModel):
    """شماره تماس مرتبط با یک مجرم."""

    criminal = models.ForeignKey(
        R4JCriminal,
        on_delete=models.CASCADE,
        related_name="phones",
        verbose_name="مجرم",
    )
    label = models.CharField(max_length=50, blank=True, verbose_name="برچسب")
    number = models.CharField(max_length=30, verbose_name="شماره")
    is_public = models.BooleanField(default=False, verbose_name="نمایش عمومی")
    notes = models.TextField(blank=True, verbose_name="توضیحات")

    class Meta:
        verbose_name = "شماره تماس مجرم"
        verbose_name_plural = "شماره‌های تماس مجرمین"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["criminal", "is_public"]),
            models.Index(fields=["number"]),
        ]

    def __str__(self) -> str:
        return f"{self.label or ''} {self.number}".strip()


# ============================================================
# R4JCriminalSocial
# ============================================================


class R4JCriminalSocial(BaseModel):
    """حساب شبکه اجتماعی مجرم."""

    criminal = models.ForeignKey(
        R4JCriminal,
        on_delete=models.CASCADE,
        related_name="socials",
        verbose_name="مجرم",
    )
    platform = models.CharField(
        max_length=20,
        choices=SocialPlatform.choices,
        verbose_name="پلتفرم",
    )
    handle_or_url = models.CharField(
        max_length=255,
        verbose_name="هندل یا URL",
    )
    is_public = models.BooleanField(default=True, verbose_name="نمایش عمومی")

    class Meta:
        verbose_name = "حساب شبکه اجتماعی مجرم"
        verbose_name_plural = "حساب‌های شبکه اجتماعی مجرمین"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["criminal", "is_public"]),
            models.Index(fields=["platform", "is_public"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["criminal", "platform", "handle_or_url"],
                name="uniq_r4j_social_per_criminal",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.platform}:{self.handle_or_url}"


# ============================================================
# R4JCriminalPhoto
# ============================================================


class R4JCriminalPhoto(BaseModel):
    """عکس‌های مرتبط با یک مجرم — حداکثر یکی primary."""

    criminal = models.ForeignKey(
        R4JCriminal,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name="مجرم",
    )
    image = models.ImageField(
        upload_to=_criminal_photo_upload_path,
        validators=[validate_photo_size, validate_photo_extension],
        verbose_name="تصویر",
    )
    caption = models.CharField(max_length=255, blank=True, verbose_name="توضیح کوتاه")
    is_primary = models.BooleanField(default=False, verbose_name="عکس اصلی")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")

    class Meta:
        verbose_name = "عکس مجرم"
        verbose_name_plural = "عکس‌های مجرمین"
        ordering = ["order", "-created_at"]
        indexes = [models.Index(fields=["criminal", "is_primary"])]
        constraints = [
            models.UniqueConstraint(
                fields=["criminal"],
                condition=models.Q(is_primary=True),
                name="uniq_r4j_primary_photo_per_criminal",
            ),
        ]

    def __str__(self) -> str:
        return f"photo#{self.pk} criminal#{self.criminal_id}"


# ============================================================
# R4JCriminalAttachment
# ============================================================


class R4JCriminalAttachment(BaseModel):
    """اسناد و فایل‌های پشتیبان پروفایل مجرم."""

    criminal = models.ForeignKey(
        R4JCriminal,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="مجرم",
    )
    file = models.FileField(
        upload_to=_criminal_attachment_upload_path,
        validators=[validate_attachment_size],
        verbose_name="فایل",
    )
    kind = models.CharField(
        max_length=20,
        choices=CriminalAttachmentKind.choices,
        default=CriminalAttachmentKind.DOCUMENT,
        verbose_name="نوع",
    )
    title = models.CharField(max_length=255, verbose_name="عنوان")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    is_public = models.BooleanField(default=False, verbose_name="نمایش عمومی")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="r4j_uploaded_attachments",
        verbose_name="آپلودکننده",
    )
    file_sha256 = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="SHA-256")
    file_size = models.PositiveBigIntegerField(default=0, verbose_name="حجم فایل")

    class Meta:
        verbose_name = "سند مجرم"
        verbose_name_plural = "اسناد مجرمین"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["criminal", "is_public", "kind"])]

    def __str__(self) -> str:
        return f"attachment#{self.pk} ({self.kind})"


# ============================================================
# R4JCriminalFieldVisibility
# ============================================================


class R4JCriminalFieldVisibility(BaseModel):
    """
    کنترل per-criminal نمایش یک فیلد به public.

    منطق:
    - اگر برای یک فیلد رکوردی وجود نداشته باشد، default سیستم اعمال می‌شود.
    - اگر وجود داشته باشد، مقدار آن override می‌کند.
    - این مدل برای فیلدهای حساس مثل national_code طراحی شده است.
    """

    criminal = models.ForeignKey(
        R4JCriminal,
        on_delete=models.CASCADE,
        related_name="field_visibility",
        verbose_name="مجرم",
    )
    field_name = models.CharField(max_length=50, verbose_name="نام فیلد")
    is_public = models.BooleanField(default=True, verbose_name="نمایش عمومی")

    class Meta:
        verbose_name = "تنظیمات نمایش فیلد"
        verbose_name_plural = "تنظیمات نمایش فیلدها"
        ordering = ["criminal_id", "field_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["criminal", "field_name"],
                name="uniq_r4j_field_visibility",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.field_name}={self.is_public} (criminal#{self.criminal_id})"


# ============================================================
# R4JReport
# ============================================================


class R4JReport(BaseModel):
    """
    گزارش community — پیشنهاد تکمیل یا اصلاح اطلاعات یک مجرم.

    workflow:
    pending -> approved | partially_approved | rejected
            -> cancel_requested -> canceled
    """

    criminal = models.ForeignKey(
        R4JCriminal,
        on_delete=models.CASCADE,
        related_name="reports",
        verbose_name="مجرم",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="r4j_reports",
        verbose_name="گزارش‌دهنده",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="یادداشت گزارش‌دهنده",
        help_text="متن آزاد گزارش‌دهنده در صورت نیاز.",
    )

    status = models.CharField(
        max_length=30,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        verbose_name="وضعیت",
    )

    admin_note = models.TextField(
        blank=True,
        verbose_name="یادداشت ادمین",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="r4j_reviewed_reports",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="زمان بررسی",
    )

    cancel_requested_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="زمان درخواست لغو",
    )
    canceled_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="زمان لغو",
    )

    class Meta:
        verbose_name = "گزارش جامعه"
        verbose_name_plural = "گزارشات جامعه"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["criminal", "status", "-created_at"]),
            models.Index(fields=["submitted_by", "status", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"report#{self.pk} criminal#{self.criminal_id} ({self.status})"


# ============================================================
# R4JReportFieldChange
# ============================================================


class R4JReportFieldChange(BaseModel):
    """
    پیشنهاد تغییر برای یک فیلد خاص از پروفایل مجرم.

    منطق:
    - ادمین می‌تواند برای هر field_change به‌صورت مستقل approve/reject کند.
    - این امکان partial-approve را روی یک گزارش فراهم می‌کند.
    - current_value_snapshot برای رفع abuse و امکان rollback نگه‌داری می‌شود.
    """

    report = models.ForeignKey(
        R4JReport,
        on_delete=models.CASCADE,
        related_name="field_changes",
        verbose_name="گزارش",
    )
    field_name = models.CharField(max_length=100, verbose_name="نام فیلد")
    suggested_value = models.TextField(verbose_name="مقدار پیشنهادی")
    current_value_snapshot = models.TextField(
        blank=True,
        verbose_name="مقدار فعلی هنگام گزارش",
    )
    status = models.CharField(
        max_length=20,
        choices=ReportFieldChangeStatus.choices,
        default=ReportFieldChangeStatus.PENDING,
        verbose_name="وضعیت",
    )
    admin_note = models.TextField(blank=True, verbose_name="یادداشت ادمین")

    class Meta:
        verbose_name = "پیشنهاد تغییر فیلد"
        verbose_name_plural = "پیشنهادات تغییر فیلد"
        ordering = ["report_id", "field_name"]
        indexes = [models.Index(fields=["report", "status"])]

    def __str__(self) -> str:
        return f"{self.field_name} -> {self.suggested_value!r} ({self.status})"




class R4JReportAliasSuggestion(BaseModel):
    """User-suggested alias to be reviewed and applied to a criminal profile."""

    report = models.ForeignKey(
        R4JReport,
        on_delete=models.CASCADE,
        related_name="alias_suggestions",
        verbose_name="گزارش",
    )
    alias = models.CharField(max_length=200, verbose_name="نام مستعار پیشنهادی")
    status = models.CharField(
        max_length=20,
        choices=ReportFieldChangeStatus.choices,
        default=ReportFieldChangeStatus.PENDING,
        verbose_name="وضعیت",
    )
    admin_note = models.TextField(blank=True, verbose_name="یادداشت ادمین")
    applied_alias = models.ForeignKey(
        R4JCriminalAlias,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_report_suggestions",
        verbose_name="نام مستعار اعمال‌شده",
    )

    class Meta:
        verbose_name = "پیشنهاد نام مستعار"
        verbose_name_plural = "پیشنهادهای نام مستعار"
        ordering = ["report_id", "id"]
        indexes = [models.Index(fields=["report", "status"], name="r4j_alias_sug_rep_stat_idx")]

    def __str__(self) -> str:
        return f"alias:{self.alias} ({self.status})"


class R4JReportPhoneSuggestion(BaseModel):
    """User-suggested phone/contact number for a criminal profile."""

    report = models.ForeignKey(
        R4JReport,
        on_delete=models.CASCADE,
        related_name="phone_suggestions",
        verbose_name="گزارش",
    )
    label = models.CharField(max_length=50, blank=True, verbose_name="برچسب")
    number = models.CharField(max_length=30, validators=[validate_phone_number], verbose_name="شماره پیشنهادی")
    is_public = models.BooleanField(default=False, verbose_name="پیشنهاد نمایش عمومی")
    notes = models.TextField(blank=True, verbose_name="توضیحات")
    status = models.CharField(
        max_length=20,
        choices=ReportFieldChangeStatus.choices,
        default=ReportFieldChangeStatus.PENDING,
        verbose_name="وضعیت",
    )
    admin_note = models.TextField(blank=True, verbose_name="یادداشت ادمین")
    applied_phone = models.ForeignKey(
        R4JCriminalPhone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_report_suggestions",
        verbose_name="شماره اعمال‌شده",
    )

    class Meta:
        verbose_name = "پیشنهاد شماره تماس"
        verbose_name_plural = "پیشنهادهای شماره تماس"
        ordering = ["report_id", "id"]
        indexes = [
            models.Index(fields=["report", "status"], name="r4j_phone_sug_rep_stat_idx"),
            models.Index(fields=["number"], name="r4j_phone_sug_number_idx"),
        ]

    def __str__(self) -> str:
        return f"phone:{self.number} ({self.status})"


class R4JReportSocialSuggestion(BaseModel):
    """User-suggested social/contact address for a criminal profile."""

    report = models.ForeignKey(
        R4JReport,
        on_delete=models.CASCADE,
        related_name="social_suggestions",
        verbose_name="گزارش",
    )
    platform = models.CharField(max_length=20, choices=SocialPlatform.choices, verbose_name="پلتفرم")
    handle_or_url = models.CharField(max_length=255, verbose_name="هندل یا URL پیشنهادی")
    is_public = models.BooleanField(default=True, verbose_name="پیشنهاد نمایش عمومی")
    status = models.CharField(
        max_length=20,
        choices=ReportFieldChangeStatus.choices,
        default=ReportFieldChangeStatus.PENDING,
        verbose_name="وضعیت",
    )
    admin_note = models.TextField(blank=True, verbose_name="یادداشت ادمین")
    applied_social = models.ForeignKey(
        R4JCriminalSocial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_report_suggestions",
        verbose_name="شبکه اجتماعی اعمال‌شده",
    )

    class Meta:
        verbose_name = "پیشنهاد شبکه اجتماعی"
        verbose_name_plural = "پیشنهادهای شبکه اجتماعی"
        ordering = ["report_id", "id"]
        indexes = [
            models.Index(fields=["report", "status"], name="r4j_soc_sug_rep_stat_idx"),
            models.Index(fields=["platform"], name="r4j_soc_sug_platform_idx"),
        ]

    def __str__(self) -> str:
        return f"social:{self.platform}:{self.handle_or_url} ({self.status})"


# ============================================================
# R4JReportAttachment
# ============================================================


class R4JReportAttachment(BaseModel):
    """فایل ضمیمه به یک گزارش."""

    report = models.ForeignKey(
        R4JReport,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="گزارش",
    )
    file = models.FileField(
        upload_to=_report_attachment_upload_path,
        validators=[validate_attachment_size],
        verbose_name="فایل",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="عنوان")
    kind = models.CharField(
        max_length=20,
        choices=CriminalAttachmentKind.choices,
        default=CriminalAttachmentKind.DOCUMENT,
        verbose_name="نوع",
    )
    file_sha256 = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="SHA-256")
    file_size = models.PositiveBigIntegerField(default=0, verbose_name="حجم فایل")
    status = models.CharField(
        max_length=20,
        choices=ReportFieldChangeStatus.choices,
        default=ReportFieldChangeStatus.PENDING,
        verbose_name="وضعیت بررسی",
    )
    admin_note = models.TextField(blank=True, verbose_name="یادداشت ادمین")
    promoted_criminal_attachment = models.ForeignKey(
        R4JCriminalAttachment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_report_attachments",
        verbose_name="سند رسمی ساخته‌شده",
    )

    class Meta:
        verbose_name = "ضمیمه گزارش"
        verbose_name_plural = "ضمائم گزارش‌ها"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["report", "kind"])]

    def __str__(self) -> str:
        return f"report-attachment#{self.pk} report#{self.report_id}"


# ============================================================
# R4JEvidenceCustodyEvent
# ============================================================


class R4JEvidenceCustodyEvent(BaseModel):
    """Append-only chain-of-custody event for R4J evidence attachments."""

    criminal_attachment = models.ForeignKey(
        R4JCriminalAttachment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="custody_events",
    )
    report_attachment = models.ForeignKey(
        R4JReportAttachment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="custody_events",
    )
    event_type = models.CharField(max_length=30, choices=EvidenceCustodyEventType.choices, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="r4j_evidence_custody_events")
    file_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "رویداد زنجیره نگهداری شواهد R4J"
        verbose_name_plural = "رویدادهای زنجیره نگهداری شواهد R4J"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["event_type", "-created_at"]), models.Index(fields=["file_sha256"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(criminal_attachment__isnull=False, report_attachment__isnull=True)
                    | models.Q(criminal_attachment__isnull=True, report_attachment__isnull=False)
                ),
                name="r4j_custody_one_evidence_target",
            )
        ]

    def __str__(self) -> str:
        return f"custody:{self.event_type}:{self.file_sha256[:12]}"

    def save(self, *args: object, **kwargs: object) -> None:
        """Keep custody events append-only."""
        if self.pk and not self._state.adding:
            raise PermissionError("ویرایش رویدادهای custody مجاز نیست.")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object):
        """Prevent deletion of custody events."""
        raise PermissionError("حذف رویدادهای custody مجاز نیست.")


# ============================================================
# R4JBounty
# ============================================================


class R4JBounty(BaseModel):
    """
    جایزه‌ی declarative یک کاربر برای یک مجرم.

    قواعد:
    - هر کاربر فقط یک bounty active per مجرم دارد (enforced by constraint).
    - حداقل مبلغ: R4J_BOUNTY_MIN_TOMAN.
    - workflow:
        active -> cancel_requested -> canceled
    - update روی همان رکورد انجام می‌شود (نه ساخت رکورد جدید).
    - تاریخچه از طریق AuditLog قابل پیگیری است.
    """

    criminal = models.ForeignKey(
        R4JCriminal,
        on_delete=models.PROTECT,
        related_name="bounties",
        verbose_name="مجرم",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="r4j_bounties",
        verbose_name="تعهدکننده",
    )
    amount_toman = models.BigIntegerField(
        validators=[MinValueValidator(R4J_BOUNTY_MIN_TOMAN)],
        verbose_name="مبلغ (تومان)",
    )
    status = models.CharField(
        max_length=20,
        choices=BountyStatus.choices,
        default=BountyStatus.ACTIVE,
        verbose_name="وضعیت",
    )

    cancel_requested_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="زمان درخواست لغو",
    )
    canceled_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="زمان لغو",
    )
    admin_note = models.TextField(blank=True, verbose_name="یادداشت ادمین")

    class Meta:
        verbose_name = "جایزه"
        verbose_name_plural = "جوایز"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["criminal", "status", "-created_at"]),
            models.Index(fields=["user", "status", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["criminal", "user"],
                condition=models.Q(status="active"),
                name="uniq_r4j_active_bounty_per_user_criminal",
            ),
        ]

    def __str__(self) -> str:
        return f"bounty#{self.pk} user#{self.user_id} -> criminal#{self.criminal_id}"
