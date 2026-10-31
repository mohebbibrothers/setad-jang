"""مدل‌های «دیوار مهربانی» — نسخه ۲ (سیاست جدید: تختهٔ نیازِ ادمین‌محور).

دامنه از یک بازار دوطرفه (کاربر آگهی می‌زند، مالک شماره‌اش را می‌دهد،
مدیریت میانی تطبیق/گزارش/ریسک) به یک **تختهٔ شفاف نیاز** تبدیل شد:

- ادمین دسته‌بندی‌ها را می‌سازد (لوازم آشپزخانه، پوشاک، ...)؛
- ادمین «نیازها» را به‌نیابِ صاحب نیاز ثبت می‌کند؛
- کاربر عمومی می‌بیند/جست‌وجو می‌کند و از راه‌های ارتباطیِ *همان آگهی*
  مستقیماً با صاحب نیاز تماس می‌گیرد؛
- گزینهٔ اختیاری «من می‌توانم کمک کنم» برای سنجش اثر و صف پیگیری ادمین.

چهار مدل کافی است: دسته، آگهی، تصویر، اعلام آمادگی. همهٔ اعتبارسنجی
تکانیکیِ تماس از `validators.py` (منبع یکتا) عبور می‌کند.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.geo import PROVINCE_CHOICES, normalize_city, normalize_province
from apps.core.geo.validators import validate_iran_place
from apps.core.models import BaseModel
from apps.kindness_wall.choices import (
    CONTACT_CHANNEL_REGISTRY,
    ListingStatus,
    OfferStatus,
    Urgency,
)
from apps.kindness_wall.managers import KindnessListingManager
from apps.kindness_wall.validators import (
    normalize_channel_value,
    validate_channel_value,
    validate_listing_image_extension,
    validate_listing_image_size,
)


def _unique_slug(*, model: type[models.Model], value: str, max_length: int) -> str:
    """تولید slug یکتا با پسوند شماره‌دار در صورت تصادم (فارسی‌پسند)."""
    base = slugify(value, allow_unicode=True)[:max_length] or uuid.uuid4().hex[:12]
    candidate = base
    suffix = 2
    manager = getattr(model, "all_objects", model.objects)
    while manager.filter(slug=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[: max_length - len(tail)]}{tail}"
        suffix += 1
    return candidate


def listing_image_upload_path(instance: KindnessListingImage, filename: str) -> str:
    """مسیر آپلود تصویر آگهی زیرپوشهٔ media (الگوی خانهٔ پروژه)."""
    return f"kindness_wall/listings/{instance.listing_id or 'new'}/images/{filename}"


def category_cover_upload_path(instance: object, filename: str) -> str:  # pragma: no cover - legacy
    """LEGACY: فقط برای import-safe بودن مهاجرت 0001 قدیمی نگه داشته شده است.

    مدل v1 «کاور دسته» داشت؛ در v2 این مفهوم حذف شده اما فایل مهاجرت ثبت‌شده
    در دیتابیس به این نام ارجاع می‌دهد و Django هنگام build_graph آن را import
    می‌کند. حذفش یعنی TypeError در هر migrate بعدی — پس این تابع باید بماند.
    """
    return f"kindness_wall/categories/covers/{filename}"


class KindnessCategory(BaseModel):
    """دستهٔ نیازها؛ صاف و ادمین‌محور (مثل: لوازم آشپزخانه، پوشاک)."""

    title = models.CharField(max_length=160, verbose_name="عنوان دسته")
    slug = models.SlugField(
        max_length=200, unique=True, allow_unicode=True, blank=True, verbose_name="اسلاگ"
    )
    description = models.TextField(blank=True, verbose_name="توضیح دسته")
    icon = models.CharField(
        max_length=8,
        blank=True,
        verbose_name="آیکون (ایموجی)",
        help_text="یک ایموجی مثل 🍳 یا 🧥 برای نمایش روی کارت دسته.",
    )
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")

    class Meta:
        verbose_name = "دسته‌بندی دیوار مهربانی"
        verbose_name_plural = "دسته‌بندی‌های دیوار مهربانی"
        ordering = ["order", "title"]
        indexes = [
            models.Index(fields=["is_active", "order"], name="kindness_cat_active_order_idx")
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """تولید خودکار slug یکتا از عنوان فارسی."""
        if not self.slug:
            self.slug = _unique_slug(model=KindnessCategory, value=self.title, max_length=200)
        super().save(*args, **kwargs)

    def open_listings(self) -> models.QuerySet:
        """کوئری آگهی‌های جاری و نامنقضی این دسته (منبع شمارندهٔ تخته)."""
        now = timezone.now()
        return self.listings.filter(
            is_active=True,
            status=ListingStatus.PUBLISHED,
        ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))


class KindnessListing(BaseModel):
    """یک «نیاز» روی دیوار؛ فقط ادمین می‌سازد و وضعیت را اداره می‌کند."""

    category = models.ForeignKey(
        KindnessCategory,
        on_delete=models.PROTECT,
        related_name="listings",
        verbose_name="دسته",
    )
    title = models.CharField(max_length=240, verbose_name="عنوان")
    slug = models.SlugField(
        max_length=300, unique=True, allow_unicode=True, blank=True, verbose_name="اسلاگ"
    )
    description = models.TextField(
        verbose_name="شرح نیاز",
        help_text="چه چیزی، برای چه منظوری و در چه حد و مقداری لازم است.",
    )
    quantity = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="تعداد/مقدار",
    )
    unit = models.CharField(max_length=20, blank=True, default="عدد", verbose_name="واحد")

    urgency = models.CharField(
        max_length=10,
        choices=Urgency.choices,
        default=Urgency.NORMAL,
        db_index=True,
        verbose_name="فوریت",
    )
    is_featured = models.BooleanField(default=False, verbose_name="ویژه (ثبیت بالای دیوار)")
    status = models.CharField(
        max_length=10,
        choices=ListingStatus.choices,
        default=ListingStatus.DRAFT,
        db_index=True,
        verbose_name="وضعیت",
    )

    beneficiary_name = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="نام/لقب صاحب نیاز",
        help_text="می‌تواند محرمانه باشد؛ مثل «خانواده‌ای در شوش».",
    )
    # ── موقعیت جغرافیایی — از دیتاستِ رسمی (apps.core.geo) ──────────────
    # هر دو خالی = «سراسر کشور» (آگهی در فیلترِ *هر* استان/شهر هم دیده می‌شود).
    # استان از لیستِ ۳۱گانه انتخاب می‌شود و شهر با فهرستِ همان استان
    # اعتبارسنجی می‌شود؛ این‌طور فیلترِ فرانت و دادهٔ ادمین همیشه یکی‌اند.
    province = models.CharField(
        max_length=60,
        blank=True,
        choices=PROVINCE_CHOICES,
        db_index=True,
        verbose_name="استان",
        help_text="خالی بگذارید تا آگهی «سراسر کشور» شود و در فیلترِ همهٔ استان‌ها دیده شود.",
    )
    city = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="شهر",
        help_text="از فهرستِ رسمیِ همان استان (خالی = همهٔ شهرهای آن استان).",
    )
    locality = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="روستا/محله",
        help_text="اختیاری — برای دقتِ بیشتر مثل «روستای قلعه‌نو».",
    )
    contact_note = models.CharField(
        max_length=240,
        blank=True,
        verbose_name="یادداشت هماهنگی",
        help_text="مثلاً: «تماس ۱۰ تا ۲۰»، «پیامکی بهتر است».",
    )

    # ── راه‌های ارتباطی؛ حداقل یکی الزامی (اعتبار در clean()/services) ──
    contact_phone = models.CharField(max_length=30, blank=True, verbose_name="شماره تماس")
    contact_bale = models.CharField(max_length=64, blank=True, verbose_name="آیدی بله")
    contact_eitaa = models.CharField(max_length=64, blank=True, verbose_name="آیدی ایتا")
    contact_telegram = models.CharField(max_length=64, blank=True, verbose_name="آیدی تلگرام")
    contact_rubika = models.CharField(max_length=64, blank=True, verbose_name="آیدی روبیکا")
    contact_instagram = models.CharField(max_length=64, blank=True, verbose_name="آیدی اینستاگرام")

    published_at = models.DateTimeField(null=True, blank=True, verbose_name="منتشر شده در")
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="انقضا")
    fulfilled_at = models.DateTimeField(null=True, blank=True, verbose_name="برطرف‌شده در")
    fulfillment_note = models.CharField(
        max_length=240,
        blank=True,
        verbose_name="روایت برطرف‌شدن",
        help_text="یک خط صادقانه برای بایگانی «داستان‌های مهربانی».",
    )
    renew_count = models.PositiveSmallIntegerField(default=0, verbose_name="بار تمدید")

    view_count = models.PositiveIntegerField(default=0, verbose_name="بازدید")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_kindness_listings",
        verbose_name="ثبت‌کننده",
    )
    search_document = models.TextField(blank=True, default="", editable=False)

    objects = KindnessListingManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "آگهی دیوار مهربانی"
        verbose_name_plural = "آگهی‌های دیوار مهربانی"
        ordering = ["-is_featured", "-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "-published_at"], name="kindness_list_status_pub_idx"),
            models.Index(fields=["category", "status"], name="kindness_list_cat_status_idx"),
            models.Index(fields=["urgency", "status"], name="kindness_list_urg_st_idx"),
            models.Index(fields=["city", "status"], name="kindness_list_city_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                name="kindness_listing_quantity_positive",
                condition=models.Q(quantity__gte=1),
            ),
        ]

    def __str__(self) -> str:
        return self.title

    # ── کانال‌های تماس: منبع یکتای خواندنی/نرمال‌سازی ──────────────
    @staticmethod
    def channel_fields() -> tuple[tuple[str, str, str, str], ...]:
        """رجیستری کانال‌ها: (نام فیلد، کد، برچسب، پیشوند لینک)."""
        return CONTACT_CHANNEL_REGISTRY

    def channel_values(self) -> dict[str, str]:
        """دیکشنری {نام فیلد: مقدار خامِ ذخیره‌شده} برای این آگهی."""
        return {
            field: getattr(self, field) for field, _code, _label, _link in self.channel_fields()
        }

    def channel_payload(self) -> list[dict[str, str]]:
        """لیست آمادهٔ پاسخ API: [{kind,label,value,link}] — فقط کانال‌های پر."""
        payload: list[dict[str, str]] = []
        for field, code, label, link_prefix in self.channel_fields():
            value = (getattr(self, field) or "").strip()
            if not value:
                continue
            link = f"{link_prefix}{value}" if link_prefix else ""
            if code == "phone":
                link = self.phone_dial_link(value)
            payload.append({"kind": code, "label": label, "value": value, "link": link})
        return payload

    @staticmethod
    def phone_dial_link(phone: str) -> str:
        """لینک شماره‌گیری بین‌المللی از شمارهٔ نرمال‌شدهٔ داخلی (0 → +98)."""
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits.startswith("0"):
            digits = "98" + digits[1:]
        return f"tel:+{digits}"

    def _normalize_place(self) -> None:
        """شکلِ رسمیِ استان/شهر/روستا را قبل از ذخیره تثبیت می‌کند.

        اگر مقدارها با دیتاست هم‌خوان نباشند (مثلاً ورودِ قدیمی یا API)،
        بی‌صدا به شکلِ رسمی برمی‌گردند؛ ناشناخته‌ها همان‌طور می‌مانند تا
        `clean()`/فرمِ ادمین خطای صریح بدهد و داده بی‌صدا پاک نشود.
        """
        province = normalize_province(self.province)
        if province:
            self.province = province
            city = normalize_city(province, self.city)
            if city:
                self.city = city
        self.locality = (self.locality or "").strip()

    def _normalize_channels(self) -> None:
        """نرمال‌سازی یکسانِ همهٔ کانال‌ها دقیقاً قبل از ذخیره (منبع یکتا)."""
        for field, code, _label, _link in self.channel_fields():
            raw = getattr(self, field) or ""
            if raw.strip():
                setattr(self, field, normalize_channel_value(kind=code, value=raw))

    @property
    def is_public(self) -> bool:
        """آیا همین آگهی الان روی تختهٔ عمومی دیده می‌شود؟"""
        if self.status != ListingStatus.PUBLISHED or not self.is_active:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    @property
    def days_left(self) -> int | None:
        """روزهای باقی‌مانده تا انقضا (None = بدون انقضا)."""
        if self.expires_at is None:
            return None
        delta = self.expires_at - timezone.now()
        return max(delta.days, 0)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """slug + نرمال‌سازی کانال‌ها + سند جستجو؛ بعد ذخیره."""
        if not self.slug:
            self.slug = _unique_slug(model=KindnessListing, value=self.title, max_length=300)
        self._normalize_channels()
        self._normalize_place()
        self.search_document = (
            f"{self.title}\n{self.description}\n{self.beneficiary_name}\n"
            f"{self.province} {self.city} {self.locality}\n"
            f"{self.category.title if self.category_id else ''}"
        )
        super().save(*args, **kwargs)

    def clean_fields(self, exclude: Any = None) -> None:
        """نرمال‌سازیِ جغرافیا **پیش از** اعتبارسنجیِ choices.

        چرا این‌جا و نه فقط در save؟ چون `full_clean` نخست اعتبارسنجیِ فیلدها
        (از جمله `choices` استان) را اجرا می‌کند و «آذربايجان شرقي» (ي عربی)
        همان‌جا رد می‌شد، هرچند در ذخیره به شکلِ رسمی نرمال می‌شد. با این
        override، ورودیِ کاربر/ادمین/API با همان یک قاعدهٔ دیتاست یکسان می‌شود
        و پیامِ خطا فقط برای مقدارِ واقعاً ناشناخته می‌ماند.
        """
        self._normalize_place()
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        """قاعدهٔ سیاست: انتشار بدون حتی یک راه تماس غیرممکن است."""
        super().clean()
        errors: dict[str, ValidationError] = {}
        # موقعیت باید با دیتاستِ رسمی هم‌خوان باشد (سراسر کشور = هر دو خالی).
        try:
            validate_iran_place(self.province, self.city)
        except ValidationError as exc:
            if hasattr(exc, "error_dict"):
                errors.update(dict(exc.error_dict))
            else:
                errors["province"] = exc
        for field, code, label, _link in self.channel_fields():
            value = getattr(self, field) or ""
            if value.strip():
                try:
                    validate_channel_value(kind=code, value=value)
                except ValidationError as exc:
                    errors[field] = ValidationError(
                        f"{label}: {exc.messages[0]}", code=exc.code if exc.code else "invalid"
                    )
        if errors:
            raise ValidationError(errors)
        if self.status != ListingStatus.DRAFT and not any(
            (getattr(self, field) or "").strip() for field, *_ in self.channel_fields()
        ):
            raise ValidationError(
                {
                    "status": ValidationError(
                        "برای هر وضعیت غیرپیش‌نویس، حداقل یک راه تماس الزامی است.",
                        code="contact_required",
                    )
                }
            )
        if self.quantity is not None and self.quantity < 1:
            raise ValidationError(
                {"quantity": ValidationError("تعداد باید حداقل ۱ باشد.", code="min_value")}
            )


class KindnessListingImage(BaseModel):
    """تصویر آگهی؛ اولین تصویر یا تصویر برگزیده به‌عنوان کاور خدمت می‌کند."""

    listing = models.ForeignKey(
        KindnessListing, on_delete=models.CASCADE, related_name="images", verbose_name="آگهی"
    )
    image = models.ImageField(
        upload_to=listing_image_upload_path,
        validators=[validate_listing_image_extension, validate_listing_image_size],
        verbose_name="فایل تصویر",
    )
    alt_text = models.CharField(max_length=240, blank=True, verbose_name="متن جایگزین")
    is_cover = models.BooleanField(default=False, verbose_name="کاور")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        verbose_name = "تصویر آگهی دیوار مهربانی"
        verbose_name_plural = "تصاویر آگهی‌های دیوار مهربانی"
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["listing", "is_cover", "order"], name="kindness_img_cover_idx")
        ]

    def __str__(self) -> str:
        return f"تصویرِ «{self.listing_id}» ({self.pk})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """قاعدهٔ کاور: اولین تصویر، کاور است؛ کاور جدید، کاورهای دیگر را خاموش می‌کند."""
        first_image = not KindnessListingImage.all_objects.filter(
            listing_id=self.listing_id
        ).exists()
        super().save(*args, **kwargs)
        if first_image and not self.is_cover:
            self.is_cover = True
            super().save(update_fields=["is_cover"])
        if self.is_cover:
            KindnessListingImage.all_objects.filter(listing_id=self.listing_id).exclude(
                pk=self.pk
            ).update(is_cover=False)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """اگر کاور حذف شد، نخستین تصویر باقی‌مانده کاور شود (دیوار بی‌تصویر نماند)."""
        was_cover = self.is_cover
        listing_id = self.listing_id
        result = super().delete(*args, **kwargs)
        if was_cover:
            successor = (
                KindnessListingImage.all_objects.filter(listing_id=listing_id)
                .order_by("order", "id")
                .first()
            )
            if successor is not None:
                successor.is_cover = True
                successor.save(update_fields=["is_cover"])
        return result


class KindnessOffer(BaseModel):
    """«من می‌توانم کمک کنم» — سیگنال اختیاری کاربرِ ثبت‌نام‌کرده.

    این رکورد جایگزین تماس نمی‌شود (تماس اصلی همان کانال‌های درج‌شدهٔ
    آگهی است)؛ فقط به صاحب نیاز/ادمین می‌گوید چند نفر داوطلب شده‌اند و
    اجازهٔ «پیگیری» می‌دهد.
    """

    listing = models.ForeignKey(
        KindnessListing, on_delete=models.CASCADE, related_name="offers", verbose_name="آگهی"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="kindness_offers",
        verbose_name="داوطلب",
    )
    message = models.TextField(
        blank=True,
        validators=[MaxLengthValidator(500)],
        verbose_name="پیام داوطلب",
        help_text="اختیاری — مثلاً «یک پتوی نو در منزل دارم».",
    )
    status = models.CharField(
        max_length=10,
        choices=OfferStatus.choices,
        default=OfferStatus.NEW,
        db_index=True,
        verbose_name="وضعیت پیگیری",
    )
    admin_note = models.CharField(max_length=240, blank=True, verbose_name="یادداشت ادمین")
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handled_kindness_offers",
        verbose_name="بررسی‌شده توسط",
    )
    handled_at = models.DateTimeField(null=True, blank=True, verbose_name="بررسی در")

    class Meta:
        verbose_name = "اعلام آمادگی دیوار مهربانی"
        verbose_name_plural = "اعلام‌های آمادگی دیوار مهربانی"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "user"], name="uniq_kindness_offer_per_user"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="kindness_offer_status_idx"),
            models.Index(fields=["listing", "status"], name="kindness_offer_listing_idx"),
        ]

    def __str__(self) -> str:
        return f"آمادگی {self.user} برای «{self.listing_id}»"
