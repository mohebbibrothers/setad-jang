"""File upload security: extension blocklist, content sniffing, and metadata stripping.

این ماژول سه لایهٔ مستقل دارد که هر کدام یک کلاس حمله را می‌بندد:

۱. **blocklist پسوند** — ارزان‌ترین سد، جلوی نام‌های آشکارا خطرناک را می‌گیرد.
۲. **امضای محتوا (magic bytes)** — نام فایل حرف کاربر است، محتوا واقعیت.
   یک فایل اجرایی که ``photo.jpg`` نام‌گذاری شده باشد از لایهٔ اول رد می‌شود
   ولی اینجا گیر می‌افتد.
۳. **پاک‌سازی متادیتا** — برای تصاویر، EXIF حذف و تصویر دوباره encode می‌شود.

چرا لایهٔ سوم برای این پروژه صرفاً «بهداشت» نیست: در اپ R4J کاربران عکس
مدرک آپلود می‌کنند. EXIF یک عکس موبایل معمولاً شامل مختصات دقیق GPS، مدل
دستگاه و زمان دقیق است. یعنی سامانه‌ای که برای گزارش‌دهی ساخته شده، بدون
اینکه کسی متوجه شود، **موقعیت مکانی گزارش‌دهنده را در فایل قابل دانلود
منتشر می‌کند**. این یک ریسک امنیتی برای *کاربر* است، نه برای سیستم — و
دقیقاً همان دسته‌ای که کاربر هیچ راهی برای محافظت از خودش در برابرش ندارد.

re-encode کردن تصویر یک فایدهٔ جانبی مهم هم دارد: فایل‌های polyglot (مثلاً
یک فایل که هم تصویر معتبر است و هم آرشیو یا اسکریپت) در فرآیند رمزگذاری
دوباره، هر چیزی جز پیکسل‌ها را از دست می‌دهند.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

logger = logging.getLogger("apps.core")


# ============================================================
# Extension blocklist
# ============================================================

# فهرست قبلی سوراخ‌های آشکاری داشت: `.htm` بسته نبود ولی `.html` بود،
# variantهای PHP (`.php5`, `.phtml`, `.phar`) و installerها و shortcutهای
# ویندوز (`.msi`, `.lnk`, `.hta`) کاملاً غایب بودند.
DANGEROUS_EXTENSIONS = {
    # اجراییِ ویندوز
    ".bat",
    ".cmd",
    ".com",
    ".cpl",
    ".dll",
    ".exe",
    ".hta",
    ".jar",
    ".js",
    ".jse",
    ".lnk",
    ".msi",
    ".msp",
    ".pif",
    ".ps1",
    ".reg",
    ".scr",
    ".vbe",
    ".vbs",
    ".wsf",
    ".wsh",
    # اسکریپت سمت سرور
    ".asp",
    ".aspx",
    ".cgi",
    ".jsp",
    ".jspx",
    ".phar",
    ".pht",
    ".php",
    ".php3",
    ".php4",
    ".php5",
    ".php7",
    ".phps",
    ".phtml",
    ".pl",
    ".py",
    ".rb",
    ".sh",
    # محتوای فعال در مرورگر — XSS از مسیر فایل سرو شده
    ".htm",
    ".html",
    ".mhtml",
    ".shtml",
    ".svg",
    ".swf",
    ".xhtml",
    ".xml",
}


# ============================================================
# Content signatures (magic bytes)
# ============================================================

# امضاهایی که هرگز نباید در یک آپلود کاربر ظاهر شوند، مستقل از نام فایل.
_FORBIDDEN_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "dos_or_windows_executable"),
    (b"\x7fELF", "elf_executable"),
    (b"\xca\xfe\xba\xbe", "java_class_or_macho_fat"),
    (b"\xfe\xed\xfa\xce", "mach_o_executable"),
    (b"\xfe\xed\xfa\xcf", "mach_o_executable"),
    (b"#!", "script_shebang"),
    (b"<?php", "php_source"),
    (b"<script", "inline_script"),
    (b"<!DOCTYPE html", "html_document"),
    (b"<html", "html_document"),
)

# امضای فرمت‌های تصویری مجاز؛ برای بررسی تطابق «پسوند اعلام‌شده» با «محتوا».
_IMAGE_SIGNATURES: tuple[tuple[bytes, frozenset[str]], ...] = (
    (b"\xff\xd8\xff", frozenset({".jpg", ".jpeg"})),
    (b"\x89PNG\r\n\x1a\n", frozenset({".png"})),
    (b"GIF87a", frozenset({".gif"})),
    (b"GIF89a", frozenset({".gif"})),
)

_SNIFF_BYTES = 512


def _read_head(file_obj, size: int = _SNIFF_BYTES) -> bytes:
    """Read the leading bytes of an upload without disturbing its position.

    بازگرداندن مکان‌نما اجباری است: این تابع در زنجیرهٔ validatorها صدا زده
    می‌شود و اگر فایل را نیمه‌خوانده رها کنیم، ذخیره‌سازی بعدی یک فایل ناقص
    می‌نویسد.
    """
    if not hasattr(file_obj, "read"):
        return b""
    position = file_obj.tell() if hasattr(file_obj, "tell") else 0
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        head = file_obj.read(size) or b""
    except (OSError, ValueError):
        return b""
    finally:
        if hasattr(file_obj, "seek"):
            file_obj.seek(position)
    return bytes(head)


def detect_forbidden_signature(head: bytes) -> str:
    """Return the name of a forbidden content signature, or an empty string."""
    stripped = head.lstrip()[:64].lower()
    for signature, label in _FORBIDDEN_SIGNATURES:
        if head.startswith(signature) or stripped.startswith(signature.lower()):
            return label
    return ""


def image_signature_matches_extension(head: bytes, extension: str) -> bool | None:
    """Check a declared image extension against the real content signature.

    Returns:
        ``True``/``False`` وقتی امضا شناخته‌شده است، و ``None`` وقتی نمی‌توان
        قضاوت کرد (مثلاً webp یا فرمتی که امضایش را نمی‌شناسیم). ``None``
        عمداً «رد نشد» است نه «مردود»: این لایه برای گرفتن جعل آشکار است،
        نه allowlist سخت‌گیرانهٔ فرمت‌ها.
    """
    for signature, extensions in _IMAGE_SIGNATURES:
        if head.startswith(signature):
            return extension in extensions
    return None


# ============================================================
# Scanner protocol and implementations
# ============================================================


@dataclass(frozen=True)
class FileScanResult:
    """Result returned by a file scanner provider."""

    clean: bool
    provider: str
    reason: str = ""


class FileScanner(Protocol):
    """Protocol for pluggable upload scanners."""

    def scan(self, file_obj) -> FileScanResult:
        """Scan uploaded file and return the verdict."""


class NoopFileScanner:
    """Scanner used before a real malware scanner is configured."""

    provider = "noop"

    def scan(self, file_obj) -> FileScanResult:
        """Return clean while preserving the scanner contract."""
        return FileScanResult(clean=True, provider=self.provider)


class ExtensionBlocklistScanner:
    """Lightweight defensive scanner blocking dangerous executable extensions."""

    provider = "extension_blocklist"

    def scan(self, file_obj) -> FileScanResult:
        """Block dangerous extensions even before malware scanning is integrated."""
        extension = Path(getattr(file_obj, "name", "") or "").suffix.lower()
        if extension in DANGEROUS_EXTENSIONS:
            return FileScanResult(clean=False, provider=self.provider, reason="dangerous_extension")
        return FileScanResult(clean=True, provider=self.provider)


class ContentSignatureScanner:
    """Reject uploads whose real content contradicts their filename.

    blocklist پسوند فقط به چیزی نگاه می‌کند که *کاربر* گفته است. این اسکنر
    به چیزی نگاه می‌کند که واقعاً در فایل هست. یک باینری ELF با نام
    ``resume.pdf`` از لایهٔ اول کاملاً بی‌دردسر رد می‌شود و اینجا می‌ماند.
    """

    provider = "content_signature"

    def scan(self, file_obj) -> FileScanResult:
        """Inspect leading bytes for forbidden or mismatched content."""
        head = _read_head(file_obj)
        if not head:
            return FileScanResult(clean=True, provider=self.provider)

        forbidden = detect_forbidden_signature(head)
        if forbidden:
            return FileScanResult(clean=False, provider=self.provider, reason=forbidden)

        extension = Path(getattr(file_obj, "name", "") or "").suffix.lower()
        if extension:
            matches = image_signature_matches_extension(head, extension)
            if matches is False:
                return FileScanResult(
                    clean=False,
                    provider=self.provider,
                    reason="content_extension_mismatch",
                )
        return FileScanResult(clean=True, provider=self.provider)


class CompositeFileScanner:
    """Run several scanners in order and fail on the first rejection.

    ترتیب اهمیت دارد: از ارزان به گران. بررسی پسوند فقط یک lookup رشته‌ای
    است، در حالی که خواندن هدر فایل I/O دارد.
    """

    provider = "composite"

    def __init__(self, scanners: tuple[FileScanner, ...]) -> None:
        self._scanners = scanners

    def scan(self, file_obj) -> FileScanResult:
        """Return the first non-clean verdict, or clean if all pass."""
        for scanner in self._scanners:
            result = scanner.scan(file_obj)
            if not result.clean:
                return result
        return FileScanResult(clean=True, provider=self.provider)


def get_file_scanner() -> FileScanner:
    """Return configured file scanner provider."""
    provider = getattr(settings, "FILE_SCAN_PROVIDER", "default")
    if provider == "noop":
        return NoopFileScanner()
    if provider == "extension_blocklist":
        return ExtensionBlocklistScanner()
    return CompositeFileScanner((ExtensionBlocklistScanner(), ContentSignatureScanner()))


def validate_uploaded_file_security(file_obj) -> None:
    """Validate uploaded file against the configured security scanner."""
    result = get_file_scanner().scan(file_obj)
    if not result.clean:
        logger.warning(
            "Upload rejected by %s scanner: reason=%s name=%s",
            result.provider,
            result.reason,
            getattr(file_obj, "name", "<unnamed>"),
        )
        raise ValidationError("فایل ضمیمه از نظر امنیتی مجاز نیست.")


# ============================================================
# Image metadata stripping
# ============================================================

# فرمت‌هایی که می‌توانیم با اطمینان دوباره encode کنیم.
_REENCODABLE_FORMATS = {"JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP", "GIF": "GIF"}

# کیفیت خروجی JPEG. ۹۰ عملاً از نظر چشمی بدون افت است و در عین حال از
# بزرگ‌شدن فایل جلوگیری می‌کند.
_JPEG_QUALITY = 90


def strip_image_metadata(file_obj) -> ContentFile | None:
    """Re-encode an uploaded image without any metadata, or return ``None``.

    ``None`` یعنی «دست نزن»: یا فایل تصویر نیست، یا فرمتش را با اطمینان
    نمی‌توانیم بازتولید کنیم. در این حالت فایل اصلی بدون تغییر ذخیره
    می‌شود — این تابع هرگز نباید باعث *از دست رفتن* آپلود شود.

    آنچه حذف می‌شود: کل EXIF (شامل GPS)، پروفایل‌های ICC، کامنت‌ها و هر
    قطعهٔ اضافی که در فایل جاسازی شده باشد.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow جزو وابستگی‌های اصلی است
        logger.warning("Pillow unavailable; image metadata not stripped")
        return None

    position = file_obj.tell() if hasattr(file_obj, "tell") else 0
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        with Image.open(file_obj) as image:
            image_format = (image.format or "").upper()
            if image_format not in _REENCODABLE_FORMATS:
                return None
            if image_format == "GIF" and getattr(image, "n_frames", 1) > 1:
                # GIF متحرک با re-encode ساده به یک فریم تبدیل می‌شود.
                return None
            image.load()
            # ساخت یک تصویر تازه و کپی کردن *فقط* پیکسل‌ها. هر چیزی که در
            # `image.info` بوده (EXIF، ICC، کامنت) عمداً منتقل نمی‌شود.
            #
            # عمداً از `putdata(list(image.getdata()))` استفاده نمی‌کنیم:
            # آن API در Pillow 12 منسوخ شده و در Pillow 14 حذف می‌شود، و
            # ضمناً کل تصویر را به‌صورت یک لیست پایتونی از پیکسل‌ها در
            # حافظه می‌سازد — برای یک عکس ۱۲ مگاپیکسلی یعنی ده‌ها مگابایت
            # شیء پایتونی. `paste` همان کار را در سطح C و بدون این هزینه
            # انجام می‌دهد.
            clean = Image.new(image.mode, image.size)
            clean.paste(image)

            buffer = BytesIO()
            save_kwargs: dict[str, object] = {}
            if image_format == "JPEG":
                if clean.mode not in {"RGB", "L", "CMYK"}:
                    clean = clean.convert("RGB")
                save_kwargs = {"quality": _JPEG_QUALITY, "optimize": True}
            clean.save(buffer, format=_REENCODABLE_FORMATS[image_format], **save_kwargs)
            buffer.seek(0)
    except Exception:
        # تصویر خراب یا فرمت غیرمنتظره: fail-open و ذخیرهٔ فایل اصلی.
        # اعتبارسنجی «واقعاً تصویر هست یا نه» کار ImageField است، نه این تابع.
        logger.info(
            "Image metadata stripping skipped for %s", getattr(file_obj, "name", "<unnamed>")
        )
        return None
    finally:
        if hasattr(file_obj, "seek"):
            file_obj.seek(position)

    return ContentFile(buffer.read(), name=getattr(file_obj, "name", "upload"))
