# apps/r4j/validators.py
"""
R4J — Reward for Justice: Custom validators.

اعتبارسنجی‌های خالص بدون هیچ business logic.
هر validator یک خطای واضح فارسی برمی‌گرداند.

اصول طراحی:
- هر validator یک مسئولیت واحد دارد.
- constantها در بالای فایل تعریف شده‌اند تا قابل تنظیم باشند.
- validators هم در model-level و هم در serializer-level قابل استفاده‌اند.
- هیچ import از سایر اپ‌ها انجام نمی‌شود (self-contained).

تغییرات نسبت به نسخه قبل:
- حذف "aliases" از REPORTABLE_CRIMINAL_FIELDS:
  aliases یک related model است (R4JCriminalAlias) و از طریق setattr
  روی Criminal قابل اعمال نیست. تغییر aliases باید از مسیر جداگانه‌ای
  (alias endpoint) انجام شود.
"""

from __future__ import annotations

import os
import re
from typing import Final

from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.core.file_security import validate_uploaded_file_security

# ============================================================
# Constants — Bounty
# ============================================================

#: حداقل مبلغ مجاز جایزه — ۵۰٬۰۰۰ تومان
R4J_BOUNTY_MIN_TOMAN: Final[int] = 50_000

# ============================================================
# Constants — Phone
# ============================================================

#: حداکثر طول شماره تلفن (شامل فرمت‌بندی)
PHONE_MAX_LENGTH: Final[int] = 30

#: حداقل تعداد ارقام خالص
PHONE_MIN_DIGITS: Final[int] = 7

#: الگوی کاراکترهای مجاز در شماره تلفن
_PHONE_ALLOWED_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[\d\s\-\+\(\)]+$")

# ============================================================
# Constants — National Code
# ============================================================

#: الگوی مجاز برای کد ملی ایرانی (دقیقاً ۱۰ رقم)
_NATIONAL_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{10}$")

# ============================================================
# Constants — File Size Limits
# ============================================================

#: حداکثر حجم عکس — ۵ مگابایت
PHOTO_MAX_SIZE_BYTES: Final[int] = 5 * 1024 * 1024

#: حداکثر حجم فایل پیوست — ۲۰ مگابایت
ATTACHMENT_MAX_SIZE_BYTES: Final[int] = 20 * 1024 * 1024

#: پسوندهای مجاز عکس
PHOTO_ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp"}
)

#: پسوندهای مجاز فایل پیوست
ATTACHMENT_ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".doc", ".docx", ".mp4", ".mp3"}
)

# ============================================================
# Constants — Social Handle
# ============================================================

#: حداکثر طول handle شبکه اجتماعی
SOCIAL_HANDLE_MAX_LENGTH: Final[int] = 255

# ============================================================
# Constants — Reportable Fields
# ============================================================

#: فیلدهای مستقیم Criminal که کاربر می‌تواند در Report پیشنهاد تغییر دهد.
#:
#: نکته طراحی:
#: - فقط فیلدهای مستقیم (scalar) روی مدل R4JCriminal مجاز هستند.
#: - "aliases" عمداً حذف شده: aliases یک related model جداست
#:   (R4JCriminalAlias) و از طریق setattr روی criminal قابل اعمال نیست.
#:   تغییر aliases از طریق admin alias endpoints انجام می‌شود.
#: - این مقدار باید با REPORTABLE_CRIMINAL_FIELDS در services.py یکسان باشد.
REPORTABLE_CRIMINAL_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "first_name",
        "last_name",
        "national_code",
        "birth_date",
        "gender",
        "country",
        "province",
        "city",
        "description",
        "crimes_summary",
        "other_info",
    }
)


# ============================================================
# Bounty validators
# ============================================================


def validate_bounty_amount(value: int) -> None:
    """
    مبلغ جایزه باید عدد مثبت و حداقل R4J_BOUNTY_MIN_TOMAN باشد.

    Args:
        value: مبلغ به تومان.

    Raises:
        ValidationError: اگر مبلغ کمتر از حداقل مجاز باشد.
    """
    if value < R4J_BOUNTY_MIN_TOMAN:
        raise ValidationError(
            f"حداقل مبلغ جایزه {R4J_BOUNTY_MIN_TOMAN:,} تومان است. "
            f"مبلغ وارد شده: {value:,} تومان.",
            code="bounty_amount_too_low",
        )


# ============================================================
# Phone validators
# ============================================================


def validate_phone_number(value: str) -> None:
    """
    اعتبارسنجی فرمت شماره تلفن.

    قوانین:
    - نمی‌تواند خالی باشد.
    - حداکثر PHONE_MAX_LENGTH کاراکتر.
    - فقط ارقام، فاصله، خط تیره، پرانتز و + مجاز هستند.
    - حداقل PHONE_MIN_DIGITS رقم خالص.

    Args:
        value: شماره تلفن خام.

    Raises:
        ValidationError: اگر فرمت نامعتبر باشد.
    """
    cleaned = value.strip()

    if not cleaned:
        raise ValidationError(
            "شماره تلفن نمی‌تواند خالی باشد.",
            code="phone_empty",
        )

    if len(cleaned) > PHONE_MAX_LENGTH:
        raise ValidationError(
            f"شماره تلفن نمی‌تواند بیشتر از {PHONE_MAX_LENGTH} کاراکتر باشد.",
            code="phone_too_long",
        )

    if not _PHONE_ALLOWED_PATTERN.match(cleaned):
        raise ValidationError(
            "شماره تلفن فقط می‌تواند شامل ارقام، +، -، ( و ) باشد.",
            code="phone_invalid_chars",
        )

    digits_only = re.sub(r"[^\d]", "", cleaned)
    if len(digits_only) < PHONE_MIN_DIGITS:
        raise ValidationError(
            f"شماره تلفن باید حداقل {PHONE_MIN_DIGITS} رقم داشته باشد.",
            code="phone_too_short",
        )


# ============================================================
# National code validators
# ============================================================


def validate_iranian_national_code(value: str) -> None:
    """
    اعتبارسنجی فرمت کد ملی ایرانی.

    فقط فرمت بررسی می‌شود (۱۰ رقم). اعتبار الگوریتمی چک نمی‌شود.
    مقدار خالی مجاز است (فیلد اختیاری برای مجرمین غیرایرانی).

    Args:
        value: کد ملی خام.

    Raises:
        ValidationError: اگر فرمت نامعتبر باشد.
    """
    if not value:
        return

    cleaned = value.strip()
    if not _NATIONAL_CODE_PATTERN.match(cleaned):
        raise ValidationError(
            "کد ملی باید دقیقاً ۱۰ رقم عددی باشد.",
            code="national_code_invalid",
        )


# ============================================================
# File validators — Photo
# ============================================================


def validate_photo_size(value: object) -> None:
    """
    حجم عکس نباید بیشتر از PHOTO_MAX_SIZE_BYTES باشد.

    Args:
        value: فایل آپلودشده (FieldFile / InMemoryUploadedFile).

    Raises:
        ValidationError: اگر حجم فایل بیش از حد مجاز باشد.
    """
    if hasattr(value, "size") and value.size > PHOTO_MAX_SIZE_BYTES:
        max_mb = PHOTO_MAX_SIZE_BYTES / (1024 * 1024)
        file_mb = value.size / (1024 * 1024)
        raise ValidationError(
            f"حجم عکس نباید بیشتر از {max_mb:.0f} مگابایت باشد. "
            f"حجم فایل ارسالی: {file_mb:.1f} مگابایت.",
            code="photo_too_large",
        )


def validate_photo_extension(value: object) -> None:
    """
    پسوند عکس باید از فرمت‌های مجاز باشد.

    فرمت‌های مجاز: jpg, jpeg, png, webp.

    Args:
        value: فایل آپلودشده.

    Raises:
        ValidationError: اگر پسوند غیرمجاز باشد.
    """
    validate_uploaded_file_security(value)
    if hasattr(value, "name") and value.name:
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in PHOTO_ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(PHOTO_ALLOWED_EXTENSIONS))
            raise ValidationError(
                f"فرمت عکس «{ext}» مجاز نیست. فرمت‌های مجاز: {allowed}",
                code="photo_invalid_extension",
            )


# ============================================================
# File validators — Attachment
# ============================================================


def validate_attachment_size(value: object) -> None:
    """
    حجم فایل پیوست نباید بیشتر از ATTACHMENT_MAX_SIZE_BYTES باشد.

    Args:
        value: فایل آپلودشده.

    Raises:
        ValidationError: اگر حجم فایل بیش از حد مجاز باشد.
    """
    if hasattr(value, "size") and value.size > ATTACHMENT_MAX_SIZE_BYTES:
        max_mb = ATTACHMENT_MAX_SIZE_BYTES / (1024 * 1024)
        file_mb = value.size / (1024 * 1024)
        raise ValidationError(
            f"حجم فایل نباید بیشتر از {max_mb:.0f} مگابایت باشد. "
            f"حجم فایل ارسالی: {file_mb:.1f} مگابایت.",
            code="attachment_too_large",
        )


def validate_attachment_extension(value: object) -> None:
    """
    پسوند فایل پیوست باید از فرمت‌های مجاز باشد.

    Args:
        value: فایل آپلودشده.

    Raises:
        ValidationError: اگر پسوند غیرمجاز باشد.
    """
    validate_uploaded_file_security(value)
    if hasattr(value, "name") and value.name:
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in ATTACHMENT_ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ATTACHMENT_ALLOWED_EXTENSIONS))
            raise ValidationError(
                f"فرمت فایل «{ext}» مجاز نیست. فرمت‌های مجاز: {allowed}",
                code="attachment_invalid_extension",
            )


# ============================================================
# Report field validators
# ============================================================


def validate_reportable_field(field_name: str) -> None:
    """
    فیلد گزارش‌شده باید از فیلدهای مجاز Criminal باشد.

    Args:
        field_name: نام فیلد پیشنهادی.

    Raises:
        ValidationError: اگر فیلد در لیست مجاز نباشد.
    """
    if field_name not in REPORTABLE_CRIMINAL_FIELDS:
        allowed = ", ".join(sorted(REPORTABLE_CRIMINAL_FIELDS))
        raise ValidationError(
            f"فیلد «{field_name}» قابل گزارش‌دهی نیست. "
            f"فیلدهای مجاز: {allowed}",
            code="field_not_reportable",
        )


# ============================================================
# Slug utilities
# ============================================================


def generate_criminal_slug(
    first_name: str,
    last_name: str,
    pk: int | None = None,
) -> str:
    """
    تولید slug برای مجرم بر اساس نام و نام خانوادگی.

    اگر pk ارائه شود، به slug اضافه می‌شود برای یکتایی بیشتر.
    collision handling در model.save() انجام می‌شود.

    فرمت:
    - بدون pk: ``donald-trump``
    - با pk: ``donald-trump-42``

    Args:
        first_name: نام.
        last_name: نام خانوادگی.
        pk: شناسه عددی (اختیاری).

    Returns:
        slug URL-safe.
    """
    parts = f"{first_name} {last_name}".strip()
    if pk is not None:
        parts = f"{parts} {pk}"
    return slugify(parts, allow_unicode=True) or f"criminal-{pk or 'new'}"
