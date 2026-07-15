"""
Parser و Normalizer برای تبدیل JSON خام محتوانگار به ساختار داخلی.

وظایف:
- تبدیل فیلدهای با نام عجیب (e19_title, e22_attachment, ...) به فیلدهای تمیز
- تشخیص نوع رسانه از پسوند فایل
- ساخت URL کامل از URL نسبی
- تبدیل تاریخ رشته‌ای به datetime

Logging:
- این ماژول تحت namespace `apps.tabyin.sync.parser` لاگ می‌گذارد
  تا با ساختار hierarchical لایه‌ی sync یکپارچه باشد.
"""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apps.tabyin.choices import MediaType

logger = logging.getLogger("apps.tabyin.sync.parser")

# Media URL برای ساخت URL کامل فایل‌ها.
#
# محتوانگار داخل JSON مقدار e22_attachment.url را به شکل نسبی برمی‌گرداند، مثلا:
#   uploads/2026/07/14/1784011112jznwyCH.png
# این مسیر روی app-service.armansky.ir عمومی نیست و 404 می‌دهد. فایل اصلی عمومی روی
# media host و زیر prefix /org/ در دسترس است:
#   https://app-media.armansky.ir/org/uploads/...
_FILE_ORIGINAL_BASE_URL = "https://app-media.armansky.ir/org/"

# نسخه schema برای URL رسانه‌ها. این مقدار در content_hash هم لحاظ می‌شود تا بعد
# از تغییر host/prefix، اجرای sync_full پیوست‌های قبلی را هم بازسازی کند.
MEDIA_URL_SCHEMA_VERSION = "armansky-media-org-v1"

# پنل مشاهده محتوا
_GALLERY_BASE_URL = "https://app.armansky.ir/panel/gallery/"

# پسوندهای شناخته‌شده
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"}
_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a"}

# Timezone تهران
_TEHRAN_TZ = ZoneInfo("Asia/Tehran")


def parse_content_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    تبدیل یک آیتم JSON خام به ساختار نرمال‌شده.

    Returns:
        dict با فیلدهای تمیز، یا None اگر آیتم نامعتبر باشد.
    """
    external_id = raw.get("id")
    if not external_id:
        logger.warning("Skipping item without id: %s", str(raw)[:100])
        return None

    title = (raw.get("e19_title") or raw.get("name") or "").strip()

    return {
        "external_id": external_id,
        "title": title,
        "description": (raw.get("e20_description") or "").strip(),
        "author_username": (raw.get("username") or "").strip(),
        "source_entity_id": raw.get("entity_id", 0),
        "source_status": raw.get("status", 0),
        "source_type": raw.get("type", 0),
        "source_created_at": _parse_datetime(raw.get("created_at")),
        "source_updated_at": _parse_datetime(raw.get("updated_at")),
        "source_url": f"{_GALLERY_BASE_URL}{external_id}",
        "raw_payload": raw,
        "attachments": _parse_attachments(raw.get("e22_attachment", [])),
    }


def _parse_attachments(raw_attachments: list[dict]) -> list[dict[str, Any]]:
    """تبدیل لیست پیوست‌های خام به ساختار نرمال."""
    result = []
    for idx, att in enumerate(raw_attachments):
        relative_url = att.get("url", "")
        if not relative_url:
            continue

        full_url = _build_original_media_url(relative_url)
        media_type = _detect_media_type(relative_url)

        result.append(
            {
                "url": full_url,
                "relative_url": relative_url,
                "media_type": media_type,
                "size": att.get("size", ""),
                "duration": att.get("duration", 0),
                "file_size": att.get("file_size", 0),
                "title": att.get("title", ""),
                "order": idx,
            }
        )

    return result


def _build_original_media_url(relative_url: str) -> str:
    """ساخت URL عمومی فایل اصلی از مسیر نسبی محتوانگار.

    ورودی معمولاً نسبی است: uploads/...
    برای مقاومت بیشتر، اگر منبع در آینده URL کامل app-service.armansky.ir/uploads/...
    برگرداند، آن را هم به media host اصلی تبدیل می‌کنیم.
    """
    cleaned = relative_url.strip()
    if not cleaned:
        return cleaned

    service_prefixes = (
        "https://app-service.armansky.ir/",
        "http://app-service.armansky.ir/",
    )
    for prefix in service_prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break

    if cleaned.startswith("https://") or cleaned.startswith("http://"):
        return cleaned

    return f"{_FILE_ORIGINAL_BASE_URL}{cleaned.lstrip('/')}"


def _detect_media_type(url: str) -> str:
    """تشخیص نوع رسانه از پسوند فایل."""
    url_lower = url.lower().split("?")[0]  # حذف query string

    for ext in _IMAGE_EXTENSIONS:
        if url_lower.endswith(ext):
            return MediaType.IMAGE

    for ext in _VIDEO_EXTENSIONS:
        if url_lower.endswith(ext):
            return MediaType.VIDEO

    for ext in _AUDIO_EXTENSIONS:
        if url_lower.endswith(ext):
            return MediaType.AUDIO

    return MediaType.OTHER


def _parse_datetime(value: str | None) -> datetime | None:
    """
    تبدیل رشته تاریخ محتوانگار به datetime aware.

    فرمت ورودی: "2026-05-06 22:44:05"
    Timezone: Asia/Tehran (فرض)
    """
    if not value:
        return None

    try:
        naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return naive.replace(tzinfo=_TEHRAN_TZ)
    except (ValueError, TypeError):
        logger.warning("Invalid datetime format: %s", value)
        return None


def extract_page_info(response_data: dict[str, Any]) -> dict[str, int]:
    """استخراج اطلاعات صفحه‌بندی از پاسخ API."""
    data = response_data.get("data", {})
    return {
        "total_pages": data.get("total_page", 1),
        "page_size": data.get("page_size", 30),
        "total_count": data.get("count", 0),
    }


def extract_items(response_data: dict[str, Any]) -> list[dict[str, Any]]:
    """استخراج لیست آیتم‌ها از پاسخ API."""
    data = response_data.get("data", {})
    return data.get("fields", [])
