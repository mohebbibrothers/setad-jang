"""Validatorهای خالصِ دیوار مهربانی — فایل، مبلغ تماس و کانال‌ها.

این ماژول عمداً هیچ وابستگی به Django ORM ندارد تا بتوان بین
model.clean، فرمِ Django Admin و سریالایزرهای DRF به‌عنوان «تنها منبع
حقیقتِ اعتبارسنجی تماس» دست‌به‌دست شود؛ هیچ‌کدام از سه مسیر نباید
قاعدهٔ جداگانه‌ای داشته باشد.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_SIZE_MB = 5

#: نگاشت ارقام فارسی/عربی به لاتین — کاربر ایرانی شماره را اغلب با
#: ارقام فارسی تایپ می‌کند؛ بدون این مرحله هیچ regex شماره‌ای رد نمی‌شود
#: ولی هیچ‌جا هم کار نمی‌کند (محل واقعی باگ قبلی جستجوی شماره در ادمین).
_PERSIAN_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_PHONE_RE = re.compile(r"^0\d{9,10}$")
_HANDLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{2,33}$")

#: پیشوند دامنه‌هایی که کاربر ممکن است به‌جای آیدی خالی پیست کند.
_HANDLE_URL_PREFIX_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?"
    r"(?:t\.me|telegram\.me|instagram\.com|eitaa\.com|bale\.ai|rubika\.ir|rubika\.me)/",
    re.IGNORECASE,
)


def to_latin_digits(value: str) -> str:
    """تبدیل ارقام فارسی/عربی به لاتین و حذف فاصله/خط تیره."""
    cleaned = (value or "").translate(_PERSIAN_DIGIT_MAP)
    return re.sub(r"[\s()\-\u202c\u200f\u200e]", "", cleaned)


def normalize_contact_phone(value: str) -> str:
    """نرمال‌سازی شماره تلفن ایران: حذف نویز، تبدیل پیش‌شماره ۰۰۹۸/+۹۸ به ۰."""
    raw = to_latin_digits(value)
    for prefix in ("0098", "+98", "98"):
        if raw.startswith(prefix) and len(raw) > len(prefix) + 9:
            raw = "0" + raw[len(prefix) :]
            break
    return raw


def normalize_contact_handle(value: str) -> str:
    """نرمال‌سازی آیدی شبکهٔ اجتماعی: حذف @، دامنه و اسلش انتهایی."""
    raw = (value or "").strip().rstrip("/")
    raw = _HANDLE_URL_PREFIX_RE.sub("", raw)
    raw = raw.lstrip("@")
    # فقطِ مسیرِ لینک را نگه می‌داریم؛ اگر کاربر لینک کامل با query داده.
    raw = raw.split("?", 1)[0].split("#", 1)[0].strip("/")
    return raw


def validate_listing_image_extension(file) -> None:
    """Validate listing image extension."""
    extension = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            f"فرمت تصویر مجاز نیست. فرمت‌های مجاز: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}"
        )


def validate_listing_image_size(file) -> None:
    """Validate listing image size."""
    if file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"حجم تصویر نباید بیشتر از {MAX_IMAGE_SIZE_MB} مگابایت باشد.")


def normalize_channel_value(*, kind: str, value: str) -> str:
    """نرمال‌سازی مقدار یک کانال تماس بر اساس نوعش (قبل از ذخیره)."""
    if kind == "phone":
        return normalize_contact_phone(value)
    return normalize_contact_handle(value)


def validate_channel_value(*, kind: str, value: str) -> None:
    """اعتبارسنجی شکلِ مقدار کانال — فقط روی مقادیرِ غیرخالی صدا زده شود."""
    if kind == "phone":
        if not _PHONE_RE.match(value):
            raise ValidationError(
                "شماره تماس باید با ۰ شروع شود و ۱۰ تا ۱۱ رقم باشد؛ مثال: ۰۹۱۲۱۲۳۴۵۶۷."
            )
        return
    if not _HANDLE_RE.match(value):
        raise ValidationError(
            "آیدی باید ۳ تا ۳۴ نویسه باشد، با حرف شروع شود و فقط شامل "
            "حروف لاتین، رقم، نقطه و زیرخط باشد."
        )


def validate_match_score(value: int) -> None:  # pragma: no cover - legacy
    """LEGACY: مهاجرت 0001 (مدل v1 تطبیق) این validator را import می‌کند.

    مفهوم match در سیاست جدید حذف شده، ولی فایل مهاجرت ثبت‌شده در
    دیتابیس باید همچنان قابل import باشد؛ این تابع عمداً هیچ محدودیتی
    اعمال نمی‌کند چون هیچ رکورد جدیدی با آن ساخته نمی‌شود.
    """
    return None


def validate_at_least_one_contact(channels: dict[str, str]) -> None:
    """قاعدهٔ طلایی نسخهٔ ۲: هر آگهیِ منتشرشده باید حداقل یک راه تماس داشته باشد."""
    if not any((value or "").strip() for value in channels.values()):
        raise ValidationError(
            "برای انتشار آگهی باید حداقل یکی از راه‌های تماس "
            "(شماره تلفن، بله، ایتا، تلگرام، روبیکا یا اینستاگرام) پر شود."
        )
