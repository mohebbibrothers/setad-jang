"""
Tests — apps.tabyin.sync.parser
"""

from __future__ import annotations

from typing import Any

from apps.tabyin.choices import MediaType
from apps.tabyin.sync.parser import parse_content_item


def _raw_item(attachment_url: str) -> dict[str, Any]:
    return {
        "id": "content-001",
        "name": "Fallback name",
        "e19_title": "عنوان تست",
        "e20_description": "توضیح تست",
        "username": "tester",
        "entity_id": 1,
        "status": 1,
        "type": 1,
        "created_at": "2026-07-14 12:00:00",
        "updated_at": "2026-07-14 12:00:00",
        "e22_attachment": [
            {
                "url": attachment_url,
                "size": "1024X1280",
                "duration": 0,
                "file_size": 90,
                "title": "",
            }
        ],
    }


def test_relative_mohtavanegar_attachment_url_is_mapped_to_public_original_media_host() -> None:
    parsed = parse_content_item(_raw_item("uploads/2026/07/14/1784011112jznwyCH.png"))

    assert parsed is not None
    attachment = parsed["attachments"][0]
    assert attachment["url"] == (
        "https://app-media.armansky.ir/org/uploads/2026/07/14/1784011112jznwyCH.png"
    )
    assert attachment["relative_url"] == "uploads/2026/07/14/1784011112jznwyCH.png"
    assert attachment["media_type"] == MediaType.IMAGE


def test_absolute_app_service_attachment_url_is_mapped_to_public_original_media_host() -> None:
    parsed = parse_content_item(
        _raw_item("https://app-service.armansky.ir/uploads/2026/07/14/1784011112jznwyCH.png")
    )

    assert parsed is not None
    assert parsed["attachments"][0]["url"] == (
        "https://app-media.armansky.ir/org/uploads/2026/07/14/1784011112jznwyCH.png"
    )


def test_unrelated_absolute_attachment_url_is_preserved() -> None:
    absolute_url = "https://cdn.example.com/uploads/file.jpg"
    parsed = parse_content_item(_raw_item(absolute_url))

    assert parsed is not None
    assert parsed["attachments"][0]["url"] == absolute_url
