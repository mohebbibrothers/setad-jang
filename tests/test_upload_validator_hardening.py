"""
پوشش کامل شاخه‌های ردکردن (rejection branches) اعتبارسنج‌های آپلود.

پس‌زمینه (آپکس ممیزی مستقل — یافتهٔ بحرانی ۳.۳):
    در `apps/r4j/validators.py` و `apps/madadkar/validators.py` تقریباً همهٔ
    خطوط `raise ValidationError` پوشش‌نداده بودند. این توابع فقط برای ردکردن
    ورودی بد وجود دارند؛ اگر شاخهٔ رد تست نشود، عملاً هیچ‌چیزِ آن تابع تست
    نشده است.

    اثبات تجربی در ممیزی: شرط whitelist پسوند پیوست به‌طور کامل غیرفعال شد
    (`if False:`) و ۸۵۳ تست سبز ماندند — یعنی هر فایلی با هر پسوندی پذیرفته
    می‌شد و هیچ تستی متوجه نمی‌شد. تست‌های این فایل دقیقاً همان شاخه‌ها را
    می‌بندند: اگر whitelist حذف یا خاموش شود، این تست‌ها قرمز می‌شوند.

نکته دربارهٔ فایل‌های آزمایشی:
    - پسوندهایی مثل `.exe`/`.sh` توسط لایهٔ file_security (بلاک‌لیست) رد
      می‌شوند که در تست‌های موجود پوشش دارد. این‌جا تمرکز روی «پسوند مجاز
      ولی در whitelist نبوده» است — مثلاً `.gif` یا `.txt` — چون فقط همین
      شاخه است که جهش قبلی را می‌گیرد.
    - محتوای فایل‌ها عمداً بایت‌های تصویر واقعی است تا «فایل سالم ولی
      با پسوند نامجاز» را شبیه‌سازی کند (قوی‌ترین حالت).
"""

from __future__ import annotations

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.madadkar.validators import (
    MAX_IMAGE_SIZE_MB,
    MAXIMUM_TOTAL_SHARES,
    MINIMUM_TOTAL_AMOUNT,
    MINIMUM_TOTAL_SHARES,
    validate_image_extension,
    validate_image_size,
    validate_share_count,
    validate_share_price_divisibility,
    validate_total_amount,
    validate_total_shares,
)
from apps.r4j.validators import (
    ATTACHMENT_MAX_SIZE_BYTES,
    PHOTO_MAX_SIZE_BYTES,
    R4J_BOUNTY_MIN_TOMAN,
    REPORTABLE_CRIMINAL_FIELDS,
    generate_criminal_slug,
    validate_attachment_extension,
    validate_attachment_size,
    validate_bounty_amount,
    validate_iranian_national_code,
    validate_phone_number,
    validate_photo_extension,
    validate_photo_size,
    validate_reportable_field,
)

# ─── Helper: ساخت بایت‌های تصویر معتبر ─────────────────────────────


def _image_bytes(fmt: str, size: int = 10) -> bytes:
    """بایت‌های یک تصویر واقعی در فرمت مشخص (کاملاً با پسوند هماهنگ)."""
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color=(200, 30, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


def _png_bytes(size: int = 10) -> bytes:
    return _image_bytes("PNG", size=size)


# ============================================================================
# R4J — photo
# ============================================================================


class TestR4JPhotoValidators:
    """شاخه‌های رد `validate_photo_*` — عکس فقط jpg/jpeg/png/webp و ≤۵MB."""

    def test_photo_with_text_extension_is_rejected(self) -> None:
        """`.txt` نه خطرناک است نه امضایش شناخته‌شده — پس فقط whitelist رد می‌کند.

        این دقیقاً شاخه‌ای است که تست جهش ممیزی آن را خاموش کرده بود
        (`if ext not in PHOTO_ALLOWED_EXTENSIONS` → بی‌اثر) و ۸۵۳ تست سبز
        ماندند.
        """
        file = SimpleUploadedFile("photo.txt", b"not an image but not dangerous either")
        with pytest.raises(ValidationError) as excinfo:
            validate_photo_extension(file)
        assert excinfo.value.code == "photo_invalid_extension"

    def test_photo_gif_content_gif_name_is_rejected(self) -> None:
        """یک فایل GIF واقعی با نام .gif — سالم ولی خارج از whitelist عکس."""
        file = SimpleUploadedFile("photo.gif", b"GIF89a" + b"\x00" * 32)
        with pytest.raises(ValidationError) as excinfo:
            validate_photo_extension(file)
        assert excinfo.value.code == "photo_invalid_extension"

    def test_photo_without_extension_is_rejected(self) -> None:
        file = SimpleUploadedFile("photo", b"x")
        with pytest.raises(ValidationError) as excinfo:
            validate_photo_extension(file)
        assert excinfo.value.code == "photo_invalid_extension"

    def test_photo_without_name_is_treated_as_unknown_and_passes_extension_check(self) -> None:
        """فایل بدون name (مثلاً FieldFile خالی) نباید خطا بدهد."""

        class _Nameless:
            size = 10

        validate_photo_extension(_Nameless())  # نباید raise شود

    def test_photo_over_size_limit_is_rejected(self) -> None:
        file = SimpleUploadedFile("photo.jpg", b"x" * (PHOTO_MAX_SIZE_BYTES + 1))
        with pytest.raises(ValidationError) as excinfo:
            validate_photo_size(file)
        assert excinfo.value.code == "photo_too_large"

    def test_photo_at_exact_size_limit_is_accepted(self) -> None:
        file = SimpleUploadedFile("photo.jpg", b"x" * PHOTO_MAX_SIZE_BYTES)
        validate_photo_size(file)  # نباید raise شود

    def test_all_whitelisted_photo_extensions_are_accepted(self) -> None:
        # محتوا باید با فرمت اعلامی هماهنگ باشد وگرنه لایهٔ content signature
        # (به‌درستی) رد می‌کند — هدف این تست پذیرش whitelist است.
        for ext, fmt in ((".jpg", "JPEG"), (".jpeg", "JPEG"), (".png", "PNG"), (".webp", "WEBP")):
            file = SimpleUploadedFile(f"photo{ext}", _image_bytes(fmt))
            validate_photo_extension(file)  # نباید raise شود


# ============================================================================
# R4J — attachment
# ============================================================================


class TestR4JAttachmentValidators:
    """شاخه‌های رد `validate_attachment_*` — پیوست فقط whitelist و ≤۲۰MB."""

    def test_attachment_with_disallowed_but_benign_extension_is_rejected(self) -> None:
        """`.txt` نه خطرناک است نه در whitelist — دقیقاً شاخهٔ جهش قبلی."""
        file = SimpleUploadedFile("evidence.txt", b"plain text evidence")
        with pytest.raises(ValidationError) as excinfo:
            validate_attachment_extension(file)
        assert excinfo.value.code == "attachment_invalid_extension"

    def test_attachment_archive_extension_is_rejected(self) -> None:
        file = SimpleUploadedFile("evidence.zip", b"PK\x03\x04fake")
        with pytest.raises(ValidationError) as excinfo:
            validate_attachment_extension(file)
        assert excinfo.value.code == "attachment_invalid_extension"

    def test_attachment_over_size_limit_is_rejected(self) -> None:
        file = SimpleUploadedFile("evidence.pdf", b"x" * (ATTACHMENT_MAX_SIZE_BYTES + 1))
        with pytest.raises(ValidationError) as excinfo:
            validate_attachment_size(file)
        assert excinfo.value.code == "attachment_too_large"

    def test_all_whitelisted_attachment_extensions_are_accepted(self) -> None:
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".pdf", ".doc", ".docx", ".mp4", ".mp3"):
            file = SimpleUploadedFile(f"evidence{ext}", b"x")
            validate_attachment_extension(file)  # نباید raise شود


# ============================================================================
# R4J — bounty / phone / national code / reportable field
# ============================================================================


class TestR4JScalarValidators:
    """شاخه‌های رد اعتبارسنج‌های غیرفایلی."""

    def test_bounty_below_minimum_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            validate_bounty_amount(R4J_BOUNTY_MIN_TOMAN - 1)
        assert excinfo.value.code == "bounty_amount_too_low"

    def test_bounty_at_minimum_is_accepted(self) -> None:
        validate_bounty_amount(R4J_BOUNTY_MIN_TOMAN)  # نباید raise شود

    def test_phone_empty_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            validate_phone_number("   ")
        assert excinfo.value.code == "phone_empty"

    def test_phone_too_long_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            validate_phone_number("0" * 31)
        assert excinfo.value.code == "phone_too_long"

    def test_phone_with_letters_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            validate_phone_number("0912abc3456")
        assert excinfo.value.code == "phone_invalid_chars"

    def test_phone_too_short_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            validate_phone_number("123456")
        assert excinfo.value.code == "phone_too_short"

    def test_valid_phone_variants_are_accepted(self) -> None:
        validate_phone_number("09123456789")
        validate_phone_number("+98 912 345 6789")
        validate_phone_number("(0912) 345-6789")

    def test_national_code_wrong_length_is_rejected(self) -> None:
        for value in ("12345", "12345678901"):
            with pytest.raises(ValidationError) as excinfo:
                validate_iranian_national_code(value)
            assert excinfo.value.code == "national_code_invalid"

    def test_national_code_with_letters_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_iranian_national_code("123456789a")

    def test_national_code_empty_is_tolerated_and_valid_code_accepted(self) -> None:
        validate_iranian_national_code("")
        validate_iranian_national_code("1234567890")

    def test_non_reportable_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            validate_reportable_field("not_a_real_field")
        assert excinfo.value.code == "field_not_reportable"

    def test_all_reportable_fields_are_accepted(self) -> None:
        for field in REPORTABLE_CRIMINAL_FIELDS:
            validate_reportable_field(field)  # نباید raise شود

    def test_criminal_slug_handles_empty_and_unicode_names(self) -> None:
        assert generate_criminal_slug("", "") == "criminal-new"
        assert generate_criminal_slug("علی", "رضایی", pk=7) == "علی-رضایی-7"


# ============================================================================
# Madadkar — campaign / share validators
# ============================================================================


class TestMadadkarScalarValidators:
    """شاخه‌های رد اعتبارسنج‌های مبلغ/سهم مددکار."""

    def test_total_amount_below_minimum_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_total_amount(MINIMUM_TOTAL_AMOUNT - 1)

    def test_total_amount_at_minimum_is_accepted(self) -> None:
        validate_total_amount(MINIMUM_TOTAL_AMOUNT)

    def test_total_shares_too_low_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_total_shares(MINIMUM_TOTAL_SHARES - 1)

    def test_total_shares_too_high_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_total_shares(MAXIMUM_TOTAL_SHARES + 1)

    def test_total_shares_at_bounds_are_accepted(self) -> None:
        validate_total_shares(MINIMUM_TOTAL_SHARES)
        validate_total_shares(MAXIMUM_TOTAL_SHARES)

    def test_share_price_divisibility_rejects_non_positive_shares(self) -> None:
        with pytest.raises(ValidationError):
            validate_share_price_divisibility(total_amount=1_000, total_shares=0)

    def test_share_price_divisibility_rejects_non_integer_price(self) -> None:
        with pytest.raises(ValidationError):
            validate_share_price_divisibility(total_amount=1_000, total_shares=3)

    def test_share_price_divisibility_accepts_exact_division(self) -> None:
        validate_share_price_divisibility(total_amount=1_000, total_shares=2)

    def test_share_count_zero_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_share_count(0)

    def test_share_count_one_is_accepted(self) -> None:
        validate_share_count(1)


# ============================================================================
# Madadkar — image validators
# ============================================================================


class TestMadadkarImageValidators:
    """شاخه‌های رد `validate_image_*` — تصویر فقط jpg/jpeg/png/webp و ≤۵MB."""

    def test_image_with_real_content_but_disallowed_extension_is_rejected(self) -> None:
        """یک PNG واقعی با نام .gif — محتوا سالم است ولی whitelist باید رد کند."""
        file = SimpleUploadedFile("banner.gif", _png_bytes())
        with pytest.raises(ValidationError):
            validate_image_extension(file)

    def test_image_text_extension_is_rejected(self) -> None:
        file = SimpleUploadedFile("banner.txt", b"x")
        with pytest.raises(ValidationError):
            validate_image_extension(file)

    def test_image_over_size_limit_is_rejected(self) -> None:
        file = SimpleUploadedFile("banner.jpg", b"x" * (MAX_IMAGE_SIZE_MB * 1024 * 1024 + 1))
        with pytest.raises(ValidationError):
            validate_image_size(file)

    def test_image_at_exact_size_limit_is_accepted(self) -> None:
        file = SimpleUploadedFile("banner.jpg", b"x" * (MAX_IMAGE_SIZE_MB * 1024 * 1024))
        validate_image_size(file)

    def test_all_whitelisted_image_extensions_are_accepted(self) -> None:
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            validate_image_extension(SimpleUploadedFile(f"banner{ext}", _png_bytes()))
