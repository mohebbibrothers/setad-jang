"""
Validators اپ مددکار.

توابع اعتبارسنجی خالص (بدون وابستگی به DB) برای فیلدهای مدل و سریالایزر.
"""

import os

from django.core.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Campaign validators
# ---------------------------------------------------------------------------

MINIMUM_TOTAL_AMOUNT = 1_000  # حداقل مبلغ کل حرکت: ۱۰۰۰ تومان
MINIMUM_TOTAL_SHARES = 1  # حداقل تعداد سهم
MAXIMUM_TOTAL_SHARES = 1_000_000  # حداکثر تعداد سهم

MINIMUM_SHARE_PRICE = 1  # حداقل قیمت هر سهم: ۱ تومان


def validate_total_amount(value: int) -> None:
    """اعتبارسنجی مبلغ کل حرکت — باید حداقل ۱۰۰۰ تومان باشد."""
    if value < MINIMUM_TOTAL_AMOUNT:
        msg = f"مبلغ کل حرکت باید حداقل {MINIMUM_TOTAL_AMOUNT:,} تومان باشد."
        raise ValidationError(msg)


def validate_total_shares(value: int) -> None:
    """اعتبارسنجی تعداد کل سهم — بین ۱ تا ۱٬۰۰۰٬۰۰۰."""
    if value < MINIMUM_TOTAL_SHARES:
        msg = f"تعداد سهم باید حداقل {MINIMUM_TOTAL_SHARES} باشد."
        raise ValidationError(msg)
    if value > MAXIMUM_TOTAL_SHARES:
        msg = f"تعداد سهم نمی‌تواند بیشتر از {MAXIMUM_TOTAL_SHARES:,} باشد."
        raise ValidationError(msg)


def validate_share_price_divisibility(total_amount: int, total_shares: int) -> None:
    """
    بررسی قابل تقسیم بودن مبلغ کل بر تعداد سهم.

    اگر باقیمانده تقسیم صفر نباشد، قیمت سهم اعشاری می‌شود
    که برای سیستم پرداخت قابل قبول نیست.
    """
    if total_shares <= 0:
        msg = "تعداد سهم باید عدد مثبت باشد."
        raise ValidationError(msg)

    if total_amount % total_shares != 0:
        msg = (
            f"مبلغ کل ({total_amount:,} تومان) باید بر تعداد سهم ({total_shares:,}) "
            f"بدون باقیمانده تقسیم شود."
        )
        raise ValidationError(msg)


# ---------------------------------------------------------------------------
# Share count validator
# ---------------------------------------------------------------------------

MINIMUM_SHARE_COUNT = 1


def validate_share_count(value: int) -> None:
    """اعتبارسنجی تعداد سهم درخواستی — حداقل ۱."""
    if value < MINIMUM_SHARE_COUNT:
        msg = f"تعداد سهم باید حداقل {MINIMUM_SHARE_COUNT} باشد."
        raise ValidationError(msg)


# ---------------------------------------------------------------------------
# Image validators
# ---------------------------------------------------------------------------

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE_MB = 5
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024


def validate_image_extension(value) -> None:
    """بررسی پسوند فایل تصویر — فقط jpg, jpeg, png, webp مجاز."""
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        msg = f"فرمت تصویر مجاز نیست. فرمت‌های مجاز: {allowed}"
        raise ValidationError(msg)


def validate_image_size(value) -> None:
    """بررسی حجم فایل تصویر — حداکثر ۵ مگابایت."""
    if value.size > MAX_IMAGE_SIZE_BYTES:
        msg = f"حجم تصویر نمی‌تواند بیشتر از {MAX_IMAGE_SIZE_MB} مگابایت باشد."
        raise ValidationError(msg)
