"""
Tests — apps.tabyin.sync.engine.SyncEngine

این تست‌ها رفتار end-to-end موتور همگام‌سازی را verify می‌کنند:
- create و update و unchanged به‌درستی شمارش شوند
- soft-delete در حالت full sync روی محتوای از-منبع-حذف‌شده اعمال شود
- توقف هوشمند incremental sync در صورت N صفحه متوالی بدون تغییر کار کند

اصول طراحی:
- mocking در سطح **Provider** انجام می‌شود (نه HTTP)، چون SyncEngine فقط با
  BaseTabyinProvider صحبت می‌کند. این الگوی Hexagonal/Ports&Adapters است.
- خود parser و hasher واقعی اجرا می‌شوند تا integration کامل verify شود.
- ساختار payload با ساختار واقعی محتوانگار هماهنگ است: parser به e19_title و
  e20_description اتکا دارد، و hasher روی همان‌ها + نام‌های مشترک hash می‌سازد.
- time.sleep داخل engine برای تست بی‌اثر می‌شود تا تست‌ها سریع و غیر-flaky باشند.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.tabyin.models import TabyinContent
from apps.tabyin.providers.base import BaseTabyinProvider
from apps.tabyin.sync.engine import SyncEngine

pytestmark = [pytest.mark.django_db]


# ============================================================
# Helpers — payload شبیه به ساختار واقعی منبع
# ============================================================


def _build_item_raw(
    external_id: str,
    *,
    title: str = "",
    description: str = "",
) -> dict[str, Any]:
    """
    یک آیتم خام هماهنگ با parser و hasher واقعی.

    parser به e19_title و e20_description اتکا دارد.
    hasher نیز همین فیلدها را در hash لحاظ می‌کند، بنابراین تغییر آن‌ها
    باعث تشخیص واقعی تغییر می‌شود.
    """
    return {
        "id": external_id,
        "name": title or f"Name for {external_id}",
        "e19_title": title or f"Title for {external_id}",
        "e20_description": description or f"Description for {external_id}",
        "username": f"user-{external_id}",
        "entity_id": 1,
        "status": 1,
        "type": 1,
        "created_at": "2026-01-01 00:00:00",
        "updated_at": "2026-01-01 00:00:00",
        "url": f"/contents/{external_id}/",
        "e22_attachment": [],
    }


def _build_page_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    شبیه‌سازی response محتوانگار برای fetch_page.
    """
    return {
        "status": True,
        "data": {
            "fields": items,
        },
    }


# ============================================================
# Fake Provider — جایگزین لایه‌ی HTTP
# ============================================================


class _FakeProvider(BaseTabyinProvider):
    """
    Fake provider برای تست SyncEngine بدون HTTP واقعی.
    """

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self._pages = pages

    def get_total_pages(self) -> int:
        return len(self._pages)

    def fetch_page(self, *, page: int) -> dict[str, Any] | None:
        if page < 1 or page > len(self._pages):
            return None
        return _build_page_response(self._pages[page - 1])

    def fetch_detail(self, *, content_id: str) -> dict[str, Any] | None:
        return None

    def close(self) -> None:
        return None


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _disable_engine_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    حذف delay واقعی بین صفحات تا تست‌ها سریع و deterministic باشند.
    """
    monkeypatch.setattr(
        "apps.tabyin.sync.engine.time.sleep",
        lambda _seconds: None,
    )


# ============================================================
# Full sync — happy path
# ============================================================


class TestSyncFull:
    """رفتار اصلی sync_full."""

    def test_creates_new_contents_from_provider(self) -> None:
        provider = _FakeProvider(
            pages=[
                [
                    _build_item_raw("ext-001"),
                    _build_item_raw("ext-002"),
                ],
            ]
        )

        stats = SyncEngine(provider=provider).sync_full()

        assert stats.pages_fetched == 1
        assert stats.created == 2
        assert stats.updated == 0
        assert stats.unchanged == 0
        assert stats.soft_deleted == 0

        external_ids = set(TabyinContent.all_objects.values_list("external_id", flat=True))
        assert external_ids == {"ext-001", "ext-002"}

    def test_existing_unchanged_content_is_counted_as_unchanged(self) -> None:
        provider_first = _FakeProvider(
            pages=[
                [_build_item_raw("ext-100", description="initial body")],
            ]
        )
        SyncEngine(provider=provider_first).sync_full()

        # بار دوم — همان payload → باید unchanged شمارش شود
        provider_second = _FakeProvider(
            pages=[
                [_build_item_raw("ext-100", description="initial body")],
            ]
        )
        stats = SyncEngine(provider=provider_second).sync_full()

        assert stats.created == 0
        assert stats.updated == 0
        assert stats.unchanged == 1

    def test_changed_content_is_updated(self) -> None:
        # description در hash لحاظ می‌شود → تغییر آن trigger update می‌کند
        provider_first = _FakeProvider(
            pages=[
                [_build_item_raw("ext-200", description="old body")],
            ]
        )
        SyncEngine(provider=provider_first).sync_full()

        provider_second = _FakeProvider(
            pages=[
                [_build_item_raw("ext-200", description="new body")],
            ]
        )
        stats = SyncEngine(provider=provider_second).sync_full()

        assert stats.created == 0
        assert stats.updated == 1
        assert stats.unchanged == 0

        refreshed = TabyinContent.all_objects.get(external_id="ext-200")
        assert refreshed.description == "new body"


# ============================================================
# Full sync — soft delete behavior
# ============================================================


class TestSyncFullSoftDelete:
    """محتواهایی که در منبع نیستند باید soft-delete شوند."""

    def test_missing_content_in_source_is_soft_deleted(self) -> None:
        provider_first = _FakeProvider(
            pages=[
                [
                    _build_item_raw("ext-A"),
                    _build_item_raw("ext-B"),
                ],
            ]
        )
        SyncEngine(provider=provider_first).sync_full()

        provider_second = _FakeProvider(
            pages=[
                [_build_item_raw("ext-A")],
            ]
        )
        stats = SyncEngine(provider=provider_second).sync_full()

        assert stats.soft_deleted == 1

        ext_a = TabyinContent.all_objects.get(external_id="ext-A")
        ext_b = TabyinContent.all_objects.get(external_id="ext-B")

        assert ext_a.is_deleted_in_source is False
        assert ext_a.is_active is True

        assert ext_b.is_deleted_in_source is True
        assert ext_b.is_active is False


# ============================================================
# Incremental sync — early stop behavior
# ============================================================


class TestSyncIncrementalEarlyStop:
    """رفتار توقف هوشمند incremental sync."""

    def test_stops_after_max_unchanged_consecutive_pages(self) -> None:
        seed_pages = [
            [_build_item_raw("ext-S1-A")],
            [_build_item_raw("ext-S2-A")],
            [_build_item_raw("ext-S3-A")],
            [_build_item_raw("ext-S4-A")],  # این صفحه نباید fetch شود
        ]
        SyncEngine(provider=_FakeProvider(pages=seed_pages)).sync_full()

        provider = _FakeProvider(pages=seed_pages)
        stats = SyncEngine(provider=provider).sync_incremental()

        # MAX_UNCHANGED_PAGES = 3 → پس باید بعد از ۳ صفحه‌ی unchanged
        # متوقف شود و چهارمی fetch نشود
        assert stats.pages_fetched == 3
        assert stats.unchanged >= 3
        assert stats.created == 0
        assert stats.updated == 0
