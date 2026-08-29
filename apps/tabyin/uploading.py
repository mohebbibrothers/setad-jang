"""
تدارکِ رسانه‌ی کاربر برای روایت‌های مردمی (Tabyin user submissions).

این ماژول تنها دروازه‌ای است که رسانه‌ی کاربر از آن عبور می‌کند و به
بایت‌های واقعی روی استوریجِ خودِ ما تبدیل می‌شود — چه از مسیر «آپلود
مستقیم» (multipart) و چه از مسیر «آینه‌سازی» (mirror) نشانی‌های بیرونی:

چرا آینه‌سازی؟  رسانه‌ای که فقط با نشانی بیرونی ثبت شود، اگر آن نشانی
فردا از دسترس برود، روایتِ منتشرشده‌ی کاربر می‌شکند. پس هر نشانی بیرونی
را با بیشترین سخت‌گیری (ضد-SSRF، سقف حجم، allowlist نوع) دانلود و روی
استوریج عمومیِ خودمان ذخیره می‌کنیم تا از آن پس با نشانیِ رسانه‌ی بعثت
(یا CDN پیکربندی‌شده) منتشر شود.

چرا زیر public/؟  سیاست کدبیس (apps.core.public_media و STORAGES
["public_media"]) فقط زیردرختِ MEDIA_ROOT/public را در معرض HTTP عمومی
قرار می‌دهد؛ باقی MEDIA_ROOT هرگز سرو نمی‌شود. ما هم همان قرارداد را
دنبال می‌کنیم تا فایل‌ها هم از nginx alias و هم از مسیر کنترل‌شده‌ی
serve_public_media قابل سرو باشند.

نکته‌ی امنیتی: SVG در هیچ کدام از مسیرها پذیرفته نمی‌شود — یک فایل SVG
می‌تواند اسکریپت حمل کند و وقتی از origin خودمان سرو شود به حمله‌ی XSS
تبدیل می‌شود.
"""

from __future__ import annotations

import io
import ipaddress
import logging
import math
import mimetypes
import socket
import tempfile
import uuid
import wave
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import BinaryIO
from urllib.parse import unquote, urljoin, urlparse

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from PIL import Image, UnidentifiedImageError

from apps.core.file_security import strip_image_metadata, validate_uploaded_file_security
from apps.tabyin.choices import MediaType

logger = logging.getLogger("apps.tabyin.uploading")

# ──────────────────────────────────────────────────────────────────────
#  قراردادِ فرمت‌ها (منبعِ واحدی که endpoint کانفیگ هم از آن تغذیه می‌کند)
# ──────────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS: dict[str, tuple[str, ...]] = {
    MediaType.IMAGE: ("jpg", "jpeg", "png", "webp", "gif", "avif", "bmp"),
    MediaType.VIDEO: ("mp4", "webm", "mov", "m4v", "mkv"),
    MediaType.AUDIO: ("mp3", "ogg", "oga", "wav", "m4a", "aac", "flac"),
    MediaType.OTHER: ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "txt"),
}

# SVG عمداً در هیچ فهرستی نیست (بردار XSS روی origin خودمان).

MEDIA_TYPE_FA_LABELS: dict[str, str] = {
    MediaType.IMAGE: "تصویر",
    MediaType.VIDEO: "ویدئو",
    MediaType.AUDIO: "صوت",
    MediaType.OTHER: "سایر",
}

# خانواده‌ی content-typeهایی که هنگام آینه‌سازی برای هر نوع قبول می‌کنیم.
_MIRROR_CONTENT_TYPES: dict[str, frozenset[str]] = {
    MediaType.IMAGE: frozenset(
        {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif", "image/bmp"}
    ),
    MediaType.VIDEO: frozenset(
        {"video/mp4", "video/webm", "video/quicktime", "video/x-matroska", "video/x-m4v"}
    ),
    MediaType.AUDIO: frozenset(
        {
            "audio/mpeg",
            "audio/ogg",
            "audio/wav",
            "audio/x-wav",
            "audio/wave",
            "audio/mp4",
            "audio/x-m4a",
            "audio/aac",
            "audio/flac",
            "audio/x-flac",
            "application/ogg",
        }
    ),
    MediaType.OTHER: frozenset(
        {
            "application/pdf",
            "application/zip",
            "application/x-zip-compressed",
            "text/plain",
            "application/msword",
            "application/vnd.ms-excel",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
    ),
}

# content-typeهایی که تحت هیچ شرایطی روی origin خودمان سرو نمی‌کنیم.
_ALWAYS_REJECTED_CONTENT_TYPES = frozenset(
    {"image/svg+xml", "text/html", "application/xhtml+xml", "text/javascript"}
)

# نگاشت content-type → پسوند، برای مواقعی که نشانی پسوند ندارد.
_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
    "image/bmp": "bmp",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "video/x-matroska": "mkv",
    "video/x-m4v": "m4v",
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
    "application/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "application/pdf": "pdf",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
    "text/plain": "txt",
}

# پیش‌فرض سقف آپلود به مگابایت (در settings با env قابل override است).
_DEFAULT_MAX_UPLOAD_MB: dict[str, int] = {
    MediaType.IMAGE: 10,
    MediaType.VIDEO: 100,
    MediaType.AUDIO: 30,
    MediaType.OTHER: 25,
}

# محدودیت‌های دفاعیِ آینه‌سازی (علاوه بر سقف حجمِ نوع رسانه)
_MIRROR_MAX_REDIRECTS = 3
_MIRROR_CHUNK_BYTES = 64 * 1024
_MIRROR_CONNECT_TIMEOUT = 5
_ALLOWED_WEB_PORTS = {80, 443, None}
_PUBLIC_MEDIA_PATH_PREFIX = "/media/"


class MirrorError(Exception):
    """خطای قابل‌پیش‌بینیِ آینه‌سازی — پیامش برای لاگ فارسی کافی است."""


@dataclass
class StoredMedia:
    """نتیجه‌ی ذخیره‌سازیِ موفقِ یک رسانه‌ی کاربر (آپلود یا آینه)."""

    url: str
    name: str
    media_type: str
    mime_type: str
    original_name: str = ""
    size: str = ""
    duration: int = 0
    file_size: int = 0  # KB — همان قراردادِ فیلد مدل
    size_bytes: int = 0
    meta: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
#  پیکربندی
# ──────────────────────────────────────────────────────────────────────


def _max_upload_mb(media_type: str) -> int:
    """سقف حجم آپلود (مگابایت) برای یک نوع رسانه؛ بد-تنظیمیِ settings پیش‌فرضِ همان نوع را برمی‌گرداند، نه انفجار."""
    configured = getattr(settings, "TABYIN_UPLOAD_MAX_MB", None) or {}
    fallback = _DEFAULT_MAX_UPLOAD_MB.get(media_type, _DEFAULT_MAX_UPLOAD_MB[MediaType.OTHER])
    try:
        value = int(configured.get(media_type, fallback))
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _max_upload_bytes(media_type: str) -> int:
    """تبدیل سقف مگابایتی به بایت — تنها نقطهٔ تبدیل واحدِ این ماژول."""
    return _max_upload_mb(media_type) * 1024 * 1024


def _mirror_max_bytes(media_type: str) -> int:
    """سقف دانلودِ آینه‌ساز: کمینهٔ سقفِ آپلودِ همان نوع و TABYIN_MIRROR_MAX_MB."""
    hard_cap_mb = getattr(settings, "TABYIN_MIRROR_MAX_MB", 120) or 120
    return min(_max_upload_mb(media_type), int(hard_cap_mb)) * 1024 * 1024


def get_upload_config_payload() -> dict:
    """قرارداد عمومیِ آپلود — همان چیزی که GET uploads/config/ برمی‌گرداند."""
    return {
        "max_attachments": 5,
        "extensions": {key: list(value) for key, value in ALLOWED_EXTENSIONS.items()},
        "max_mb": {
            key: _max_upload_mb(key)
            for key in (MediaType.IMAGE, MediaType.VIDEO, MediaType.AUDIO, MediaType.OTHER)
        },
        "labels": dict(MEDIA_TYPE_FA_LABELS),
    }


# ──────────────────────────────────────────────────────────────────────
#  نام‌گذاری و نشانیِ عمومی
# ──────────────────────────────────────────────────────────────────────


def _public_storage():
    """استوریج عمومیِ رسانه؛ resolve در زمان فراخوانی (نه import) تا override در تست/استقرار کار کند."""
    return storages["public_media"]


def build_media_name(kind: str, ext: str, *, user_pk: int | None = None) -> str:
    """نام یکتا در استوریج عمومی — زیردرخت tabyin/."""
    owner = str(user_pk) if user_pk else "shared"
    return f"tabyin/{kind}/{owner}/{uuid.uuid4().hex}.{ext}"


def public_url_for_name(name: str) -> str:
    """
    نشانیِ عمومیِ فایل ذخیره‌شده.

    حالت محلی: مسیر نسبی /media/public/… (فرانت با origin خودش مطلقش می‌کند).
    اگر TABYIN_PUBLIC_MEDIA_BASE_URL (مثلا CDN خودمان) تنظیم شده باشد،
    به‌جای مسیر نسبی، نشانی مطلق CDN ساخته می‌شود.
    """
    url = _public_storage().url(name)
    cdn_base = str(getattr(settings, "TABYIN_PUBLIC_MEDIA_BASE_URL", "") or "").rstrip("/")
    if cdn_base and url.startswith("/"):
        return f"{cdn_base}{url}"
    return url


def local_media_name_from_url(raw_url: str) -> str | None:
    """
    اگر نشانی به رسانه‌ی عمومیِ خودمان اشاره کند، نامِ داخلیِ استوریج را
    برمی‌گرداند؛ در غیر این صورت None.

    قابل‌قبول: مسیر نسبی /media/… یا نشانی مطلقِ میزبانِ خودمان
    (TABYIN_LOCAL_MEDIA_HOSTS و میزبانِ CDN پیکربندی‌شده).
    """
    if not raw_url:
        return None
    parsed = urlparse(raw_url.strip())
    path = unquote(parsed.path or "")
    prefix = _PUBLIC_MEDIA_PATH_PREFIX + "public/"
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in ("http", "https"):
            return None
        hosts = {h.strip().lower() for h in getattr(settings, "TABYIN_LOCAL_MEDIA_HOSTS", []) if h}
        cdn_base = str(getattr(settings, "TABYIN_PUBLIC_MEDIA_BASE_URL", "") or "").strip()
        if cdn_base:
            cdn_host = urlparse(cdn_base).netloc.lower()
            if cdn_host:
                hosts.add(cdn_host)
        if parsed.netloc.lower() not in hosts:
            return None
    if not path.startswith(prefix):
        return None
    name = path[len(prefix) :]
    return name or None


def is_local_media_url(raw_url: str) -> bool:
    """آیا URL به رسانهٔ لوکِ خودمان (رسانهٔ محلی) اشاره می‌کند؟"""
    return local_media_name_from_url(raw_url) is not None


# ──────────────────────────────────────────────────────────────────────
#  استخراج متادیتا — همان فیلدهایی که برای محتوای منبع خارجی پر می‌شود
# ──────────────────────────────────────────────────────────────────────


def sniff_media_type_from_filename(filename: str) -> str | None:
    """نوع رسانه از پسوندِ نام فایل؛ None یعنی فرمتِ ناشناخته (مسئولیتِ رد با اعتبارسنجی است)."""
    ext = filename.rsplit(".", maxsplit=1)[-1].lower() if "." in filename else ""
    for media_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return media_type
    return None


def _extract_image_dimensions(file_obj: BinaryIO) -> str:
    """ابعاد WxH از هدرِ تصویر؛ verify() پیش از decode برای ردِ زودهنگامِ فایلِ نیمه‌خراب."""
    file_obj.seek(0)
    with Image.open(file_obj) as img:
        img.verify()
    file_obj.seek(0)
    with Image.open(file_obj) as img:
        return f"{img.width}X{img.height}"


def _extract_wav_duration(file_obj: BinaryIO) -> int:
    """ثانیه‌های WAV از هدرِ wave؛ هر خطای فایل صفر برمی‌گرداند (متادیتای ناقص نباید آپلود را بشکند)."""
    try:
        file_obj.seek(0)
        with wave.open(file_obj, "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate() or 1
            return max(0, round(frames / rate))
    except (wave.Error, EOFError, OSError):
        return 0


def _extract_mp4_duration(file_obj: BinaryIO) -> int:
    """
    خواندنِ duration از جعبه‌ی moov/mvhd در ISO-BMFF (mp4/m4v/mov).

    پیاده‌سازیِ حداقلی و بدون وابستگی: روی هدرِ جعبه‌ها رد می‌شویم تا
    moov پیدا شود و بعد mvhd؛ اگر هر چیزی غافلگیرمان کرد بی‌صدا ۰
    برمی‌گردانیم — متادیتای ناقص هرگز نباید آپلود کاربر را بشکند.
    """
    try:
        file_obj.seek(0, 2)
        end = file_obj.tell()
        file_obj.seek(0)

        def read_boxes(limit: int) -> Iterable[tuple[bytes, int, int]]:
            pos = 0
            while pos + 8 <= end and pos < limit:
                file_obj.seek(pos)
                header = file_obj.read(8)
                if len(header) < 8:
                    return
                size = int.from_bytes(header[:4], "big")
                box_type = header[4:8]
                header_size = 8
                if size == 1:
                    large = file_obj.read(8)
                    if len(large) < 8:
                        return
                    size = int.from_bytes(large, "big")
                    header_size = 16
                elif size == 0:
                    size = end - pos
                if size < header_size:
                    return
                yield box_type, pos + header_size, pos + size
                pos += size

        for box_type, payload_start, payload_end in read_boxes(limit=end):
            if box_type != b"moov":
                continue
            moov_end = payload_end
            # داخل moov دنبال mvhd می‌گردیم.
            pos = payload_start
            while pos + 8 <= moov_end:
                file_obj.seek(pos)
                header = file_obj.read(8)
                if len(header) < 8:
                    break
                size = int.from_bytes(header[:4], "big")
                inner_type = header[4:8]
                if size < 8:
                    break
                if inner_type == b"mvhd":
                    body = file_obj.read(min(size - 8, 32))
                    if len(body) < 20:
                        return 0
                    version = body[0]
                    if version == 1 and len(body) >= 32:
                        timescale = int.from_bytes(body[20:24], "big")
                        duration = int.from_bytes(body[24:32], "big")
                    else:
                        timescale = int.from_bytes(body[12:16], "big")
                        duration = int.from_bytes(body[16:20], "big")
                    if timescale <= 0:
                        return 0
                    return max(0, round(duration / timescale))
                pos += size
            return 0
        return 0
    except (OSError, ValueError):
        return 0


def extract_media_meta(file_obj: BinaryIO, media_type: str, size_bytes: int) -> dict:
    """
    متادیتای پیوست در قالبِ قراردادِ مدل:
      size      ابعاد «WxH» با بزرگِ X (مانند 1920X1080)
      duration  ثانیه (فقط صوت/ویدئو — در صورت امکان)
      file_size کیلوبایت (سقف‌گرد، حداقل ۱ برای فایلِ غیرخالی)

    برای تصویر، سلامت فایل هم همین‌جا اثبات می‌شود؛ تصویر خراب
    ValueError می‌دهد تا هم آپلود و هم آینه آن را رد کنند.
    """
    meta = {
        "size": "",
        "duration": 0,
        "file_size": max(1, math.ceil(size_bytes / 1024)) if size_bytes else 0,
    }
    try:
        if media_type == MediaType.IMAGE:
            meta["size"] = _extract_image_dimensions(file_obj)
        elif media_type == MediaType.AUDIO:
            meta["duration"] = _extract_wav_duration(file_obj)
        elif media_type == MediaType.VIDEO:
            meta["duration"] = _extract_mp4_duration(file_obj)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        if media_type == MediaType.IMAGE:
            raise ValueError("فایل تصویر سالم نیست یا قابل خواندن نیست.") from exc
    finally:
        with suppress(OSError, ValueError):
            file_obj.seek(0)
    return meta


# ──────────────────────────────────────────────────────────────────────
#  آپلود مستقیم
# ──────────────────────────────────────────────────────────────────────


def _formats_hint() -> str:
    """رشتهٔ راهنمای فرمت‌ها برای پیام‌های user-facing (لیست پسوندها با برچسبِ فارسیِ هر نوع)."""
    parts = []
    for media_type in (MediaType.IMAGE, MediaType.VIDEO, MediaType.AUDIO, MediaType.OTHER):
        exts = "، ".join(ALLOWED_EXTENSIONS[media_type])
        parts.append(f"{MEDIA_TYPE_FA_LABELS[media_type]}: {exts}")
    return " | ".join(parts)


def store_user_upload(*, uploaded_file, user) -> StoredMedia:
    """
    اعتبارسنجی و ذخیره‌ی آپلود مستقیم کاربر روی استوریج عمومی.

    خطاها به‌شکل django ValidationError با پیام فارسی برمی‌گردند تا لایه‌ی
    view همان را در envelope خطا بگذارد.
    """
    original_name = (getattr(uploaded_file, "name", "") or "").strip()
    media_type = sniff_media_type_from_filename(original_name)
    if media_type is None:
        raise ValidationError(
            {"file": f"فرمت فایل مجاز نیست. فرمت‌های قابل‌قبول — {_formats_hint()}"}
        )

    size_bytes = int(getattr(uploaded_file, "size", 0) or 0)
    if size_bytes <= 0:
        raise ValidationError({"file": "فایل خالی است؛ فایل معتبر بارگذاری کن."})
    max_bytes = _max_upload_bytes(media_type)
    if size_bytes > max_bytes:
        raise ValidationError(
            {
                "file": (
                    f"حجم فایل از سقف مجاز {_max_upload_mb(media_type)} مگابایت برای "
                    f"{MEDIA_TYPE_FA_LABELS[media_type]} بیشتر است."
                )
            }
        )

    # لایهٔ امنیتیِ مشترکِ پروژه (بلاک‌لیست پسوند + امضای محتوا / magic bytes)
    # — همان زنجیره‌ای که فرم‌های دیگر سایت (r4j، پشتیبانی) از آن عبور می‌کنند.
    validate_uploaded_file_security(uploaded_file)

    ext = original_name.rsplit(".", maxsplit=1)[-1].lower()
    try:
        meta = extract_media_meta(uploaded_file, media_type, size_bytes)
    except ValueError as exc:
        raise ValidationError({"file": str(exc)}) from exc

    payload = uploaded_file
    if media_type == MediaType.IMAGE:
        # EXIF و متادیتای بالقوهً حساسِ تصویر (GPS، دستگاه، …) پاک می‌شود؛
        # خروجی ترکیده‌ی بازکدگذاری، آنچه سرو می‌شود است.
        stripped = strip_image_metadata(uploaded_file)
        if stripped is not None:
            payload = stripped
            size_bytes = int(stripped.size)
            meta["file_size"] = max(1, math.ceil(size_bytes / 1024))

    name = build_media_name("uploads", ext, user_pk=getattr(user, "pk", None))
    # برخی wrapperها seek ندارند — ساکت رد می‌شویم.
    with suppress(OSError, ValueError):
        payload.seek(0)
    saved_name = _public_storage().save(name, payload)
    mime_type = (getattr(uploaded_file, "content_type", "") or "").strip().lower()
    if not mime_type:
        mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"

    return StoredMedia(
        url=public_url_for_name(saved_name),
        name=saved_name,
        media_type=media_type,
        mime_type=mime_type,
        original_name=original_name,
        size=meta["size"],
        duration=meta["duration"],
        file_size=meta["file_size"],
        size_bytes=size_bytes,
    )


# ──────────────────────────────────────────────────────────────────────
#  آینه‌سازی نشانی‌های بیرونی — دانلود دفاعی با سدِ SSRF
# ──────────────────────────────────────────────────────────────────────


def _assert_public_ip_literal(hostname: str) -> bool:
    """اگر hostname یک IP literal بود، عمومی‌بودنش را تصدیق و True می‌دهد."""
    cleaned = hostname.strip("[]")
    try:
        ip = ipaddress.ip_address(cleaned)
    except ValueError:
        return False
    if not ip.is_global:
        raise MirrorError("نشانی به یک نشستِ غیرعمومی (شبکه‌ی داخلی) اشاره دارد.")
    return True


def _assert_public_web_url(url: str) -> None:
    """
    سدِ SSRF: فقط http/https عمومی.

    - طرح‌های دیگر (file، ftp، gopher، …) رد می‌شوند؛
    - userinfo در نشانی ممنوع است (نشت credential در لاگ)؛
    - فقط پورت‌های 80/443؛
    - hostname یا IP literalِ عمومی باشد و اگر نام دامنه است، تمام
      نشست‌های resolve‌شده‌اش عمومی باشند (تا DNS rebound به 127.x یا
      192.168.x ممکن نشود).
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise MirrorError("فقط نشانی‌های http/https قابل آینه‌سازی هستند.")
    if not parsed.hostname:
        raise MirrorError("نشانی معتبر نیست.")
    if parsed.username or parsed.password:
        raise MirrorError("نشانی‌های دارای کاربر/گذرواژه (userinfo) پذیرفته نیستند.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise MirrorError("پورت نشانی معتبر نیست.") from exc
    if port not in _ALLOWED_WEB_PORTS:
        raise MirrorError("فقط پورت‌های ۸۰ و ۴۴۳ برای آینه‌سازی مجازند.")

    hostname = parsed.hostname.strip().lower().rstrip(".")
    if _assert_public_ip_literal(hostname):
        return
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise MirrorError("دامنه‌ی نشانی قابل تبدیل به نشست نیست.") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise MirrorError("برای این دامنه هیچ نشستی پیدا نشد.")
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise MirrorError("نشستِ نامعتبر برای دامنه.") from exc
        if not ip.is_global:
            raise MirrorError("دامنه به یک نشستِ غیرعمومی (شبکه‌ی داخلی) اشاره می‌کند.")


def _open_mirror_stream(url: str) -> requests.Response:
    """
    بازکردنِ جریان دانلود با دنبال‌کردنِ دستیِ redirect تا ۳ پرش — هر پرش
    دوباره از سدِ SSRF رد می‌شود (requests به‌تنهایی این کار را نمی‌کند).
    """
    current = url
    timeout = getattr(settings, "TABYIN_MIRROR_TIMEOUT_SECONDS", 25) or 25
    for _ in range(_MIRROR_MAX_REDIRECTS + 1):
        _assert_public_web_url(current)
        try:
            response = requests.get(
                current,
                stream=True,
                timeout=(_MIRROR_CONNECT_TIMEOUT, timeout),
                allow_redirects=False,
                headers={
                    "User-Agent": "BesatMediaMirror/1.0 (+https://besat.me)",
                    "Accept": "image/*,video/*,audio/*,application/*;q=0.8,*/*;q=0.5",
                },
            )
        except requests.RequestException as exc:
            raise MirrorError("دانلود از نشانی داده‌شده ممکن نشد.") from exc
        if response.status_code in (301, 302, 303, 307, 308):
            location = (response.headers.get("Location") or "").strip()
            response.close()
            if not location:
                raise MirrorError("تغییرمسیرِ بی‌مقصد از سوی سرور مبدأ.")
            current = urljoin(current, location)
            continue
        if response.status_code != 200:
            response.close()
            raise MirrorError(f"سرور مبدأ وضعیت {response.status_code} برگرداند.")
        return response
    raise MirrorError("زنجیره‌ی تغییرمسیر بیش از حد مجاز است.")


def _detect_remote_kind(content_type: str, ext: str) -> str | None:
    """نوعِ واقعیِ محتوای راه دور را از mime یا پسوند حدس می‌زند."""
    if content_type:
        for media_type, allowed in _MIRROR_CONTENT_TYPES.items():
            if content_type in allowed:
                return media_type
    if ext:
        for media_type, extensions in ALLOWED_EXTENSIONS.items():
            if ext in extensions:
                return media_type
    return None


def mirror_attachment_to_local(attachment) -> bool:
    """
    دانلودِ دفاعیِ پیوستِ نشانی‌محور و انتشار از روی رسانه‌ی خودمان.

    موفق: url به نشانیِ محلیِ ما تبدیل، متادیتا پر و mirror_status=mirrored
    می‌شود و نشانی اصلی در origin_url می‌ماند.
    ناموفق: mirror_status=failed می‌شود اما نشانیِ اصلی دست‌نخورده باقی
    می‌ماند تا محتوا — با graceful degradation — همچنان قابل نمایش باشد.
    خروجی True/False نشان‌دهنده‌ی موفقیت است؛ هرگز raise نمی‌کند.
    """
    remote_url = (attachment.origin_url or attachment.url or "").strip()
    declared = attachment.media_type or MediaType.OTHER
    declared = declared if declared in ALLOWED_EXTENSIONS else MediaType.OTHER
    if not remote_url or is_local_media_url(remote_url):
        return True

    def _fail() -> bool:
        attachment.mirror_status = "failed"
        attachment.save(update_fields=["mirror_status", "updated_at"])
        return False

    try:
        response = _open_mirror_stream(remote_url)
    except MirrorError as exc:
        logger.warning("Tabyin mirror blocked for attachment %s: %s", attachment.pk, exc)
        return _fail()

    with response:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type in _ALWAYS_REJECTED_CONTENT_TYPES:
            logger.warning(
                "Tabyin mirror rejected content-type %s for attachment %s",
                content_type,
                attachment.pk,
            )
            return _fail()

        remote_path_ext = ""
        try:
            path = unquote(urlparse(response.url).path or "")
            if "." in path.rsplit("/", maxsplit=1)[-1]:
                remote_path_ext = path.rsplit(".", maxsplit=1)[-1].lower()
        except (ValueError, IndexError):
            remote_path_ext = ""

        detected = _detect_remote_kind(content_type, remote_path_ext)
        if detected is not None and detected != declared:
            logger.warning(
                "Tabyin mirror type mismatch for attachment %s: declared=%s detected=%s",
                attachment.pk,
                declared,
                detected,
            )
            return _fail()

        if remote_path_ext not in ALLOWED_EXTENSIONS[declared]:
            mapped = _CONTENT_TYPE_TO_EXT.get(content_type)
            ext = mapped if mapped and mapped in ALLOWED_EXTENSIONS[declared] else ""
        else:
            ext = remote_path_ext
        if not ext:
            logger.warning(
                "Tabyin mirror could not determine a safe extension for attachment %s",
                attachment.pk,
            )
            return _fail()

        cap = _mirror_max_bytes(declared)
        declared_length = response.headers.get("Content-Length")
        if declared_length and declared_length.isdigit() and int(declared_length) > cap:
            logger.warning("Tabyin mirror oversize (header) for attachment %s", attachment.pk)
            return _fail()

        received = 0
        try:
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as buffer:
                for chunk in response.iter_content(chunk_size=_MIRROR_CHUNK_BYTES):
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > cap:
                        raise MirrorError("حجم فایل از سقف مجازِ آینه‌سازی بیشتر است.")
                    buffer.write(chunk)

                if received == 0:
                    logger.warning("Tabyin mirror got empty body for attachment %s", attachment.pk)
                    return _fail()

                buffer.seek(0)
                try:
                    meta = extract_media_meta(buffer, declared, received)
                except ValueError as exc:
                    logger.warning("Tabyin mirror meta failed for %s: %s", attachment.pk, exc)
                    return _fail()

                # اسکن امنیتیِ خطِ اول روی head محتوای دریافتی (امضای MZ/ELF/اسکریپت…)
                # — حتی اگر سرور مبدأ content-type را جعل کرده باشد، بدافزار به
                # origin خودمان راه پیدا نمی‌کند.
                buffer.seek(0)
                probe = io.BytesIO(buffer.read(4096))
                probe.name = f"mirror.{ext}"
                try:
                    validate_uploaded_file_security(probe)
                except ValidationError as exc:
                    logger.warning(
                        "Tabyin mirror blocked by security scanner for %s: %s",
                        attachment.pk,
                        exc.messages,
                    )
                    return _fail()

                name = build_media_name("shared", ext)
                buffer.seek(0)
                saved_name = _public_storage().save(name, buffer)
        except (requests.RequestException, MirrorError) as exc:
            logger.warning("Tabyin mirror download failed for %s: %s", attachment.pk, exc)
            return _fail()

    attachment.origin_url = remote_url
    attachment.url = public_url_for_name(saved_name)
    attachment.relative_url = attachment.url
    attachment.mirror_status = "mirrored"
    attachment.mime_type = content_type or mimetypes.guess_type(saved_name)[0] or ""
    attachment.size = meta["size"]
    attachment.duration = meta["duration"]
    attachment.file_size = meta["file_size"]
    attachment.save(
        update_fields=[
            "origin_url",
            "url",
            "relative_url",
            "mirror_status",
            "mime_type",
            "size",
            "duration",
            "file_size",
            "updated_at",
        ]
    )
    logger.info(
        "Tabyin attachment %s mirrored locally (%d bytes → %s)",
        attachment.pk,
        received,
        attachment.url,
    )
    return True


def local_attachment_meta(name: str, media_type: str) -> dict | None:
    """
    متادیتای یک فایلِ ازپیش‌ذخیره‌شده روی استوریج عمومی — برای وقتی که
    پیوستِ ارسالی از همان ابتدا نشانیِ محلی (نتیجه‌ی آپلود مستقیم) است.
    هرگز raise نمی‌کند؛ در مشکل، None برمی‌گرداند.
    """
    storage = _public_storage()
    try:
        if not storage.exists(name):
            return None
        size_bytes = storage.size(name)
        with storage.open(name, "rb") as fh:
            media_type = media_type if media_type in ALLOWED_EXTENSIONS else MediaType.OTHER
            return extract_media_meta(fh, media_type, size_bytes)
    except (OSError, ValueError):
        return None
