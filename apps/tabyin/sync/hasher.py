"""
تولید هش برای تشخیص تغییر واقعی محتوا.

به جای مقایسه فیلد‌به‌فیلد، یک SHA-256 از فیلدهای کلیدی می‌سازیم.
اگر هش عوض نشده باشد = محتوا تغییر نکرده = نیازی به UPDATE نیست.
"""

import hashlib
import json
from typing import Any


def compute_content_hash(data: dict[str, Any]) -> str:
    """
    هش SHA-256 از فیلدهای معنادار محتوا.

    فقط فیلدهایی که تغییرشان مهم است را هش می‌کنیم:
    - عنوان، توضیحات، نویسنده
    - پیوست‌ها (url, duration, file_size)
    - وضعیت و نوع
    - تاریخ آخرین ویرایش
    """
    significant_fields = {
        "title": data.get("e19_title", "") or data.get("name", ""),
        "description": data.get("e20_description", ""),
        "username": data.get("username", ""),
        "status": data.get("status"),
        "type": data.get("type"),
        "updated_at": data.get("updated_at", ""),
        "attachments": _normalize_attachments(data.get("e22_attachment", [])),
    }

    # JSON با sort_keys برای deterministic output
    raw = json.dumps(significant_fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_attachments(attachments: list[dict]) -> list[dict]:
    """نرمال‌سازی لیست پیوست‌ها برای هش یکسان."""
    normalized = []
    for att in attachments:
        normalized.append(
            {
                "url": att.get("url", ""),
                "duration": att.get("duration", 0),
                "file_size": att.get("file_size", 0),
                "size": att.get("size", ""),
            }
        )
    return normalized
