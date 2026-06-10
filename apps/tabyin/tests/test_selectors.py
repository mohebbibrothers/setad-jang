"""
Tests — apps.tabyin.selectors

این تست‌ها رفتار لایه‌ی selector تبیین را در سطح unit/integration verify می‌کنند:
- فیلتر شدن صحیح محتوای غیرفعال یا حذف‌شده در منبع از لیست عمومی
- دسترسی کامل ادمین به همه‌ی محتواها
- رفتار get-by-external-id در حالات فعال/غیرفعال/ناموجود
- رفتار cache در get_public_content_detail_cached (miss → hit)
- رفتار set/get هم‌خانواده برای page-level cache

اصول طراحی تست‌ها:
- داده‌ها فقط از طریق factory-boy ساخته می‌شوند.
- هیچ ORM call مستقیم برای داده‌سازی در تست انجام نمی‌شود.
- assertها deterministic و نیازمند فریز زمان نیستند.
"""

from __future__ import annotations

import pytest

from apps.tabyin import selectors
from apps.tabyin.models import TabyinContent
from tests.factories import TabyinContentFactory

pytestmark = [pytest.mark.django_db]


# ============================================================
# Public list — visibility rules
# ============================================================


class TestGetPublicContents:
    """رفتار queryset عمومی محتواهای تبیین."""

    @pytest.mark.unit
    def test_returns_only_active_and_not_deleted_in_source(self) -> None:
        active = TabyinContentFactory(is_active=True, is_deleted_in_source=False)
        TabyinContentFactory(is_active=False, is_deleted_in_source=False)
        TabyinContentFactory(is_active=True, is_deleted_in_source=True)

        qs = selectors.get_public_contents()

        external_ids = list(qs.values_list("external_id", flat=True))
        assert external_ids == [active.external_id]

    @pytest.mark.unit
    def test_returns_empty_when_no_visible_content_exists(self) -> None:
        TabyinContentFactory(is_active=False)
        TabyinContentFactory(is_deleted_in_source=True)

        qs = selectors.get_public_contents()

        assert qs.count() == 0


# ============================================================
# Admin list — full visibility
# ============================================================


class TestGetAdminContents:
    """ادمین باید به تمام محتواها دسترسی داشته باشد."""

    @pytest.mark.unit
    def test_returns_active_inactive_and_deleted_in_source(self) -> None:
        active = TabyinContentFactory(is_active=True, is_deleted_in_source=False)
        inactive = TabyinContentFactory(is_active=False, is_deleted_in_source=False)
        deleted_in_source = TabyinContentFactory(is_active=True, is_deleted_in_source=True)

        qs = selectors.get_admin_contents()

        external_ids = set(qs.values_list("external_id", flat=True))
        assert external_ids == {
            active.external_id,
            inactive.external_id,
            deleted_in_source.external_id,
        }


# ============================================================
# Public get_by_external_id
# ============================================================


class TestGetPublicContentByExternalId:
    """رفتار جزئیات محتوای عمومی."""

    @pytest.mark.unit
    def test_returns_content_when_active_and_not_deleted(self) -> None:
        content = TabyinContentFactory(
            is_active=True,
            is_deleted_in_source=False,
        )

        result = selectors.get_public_content_by_external_id(content.external_id)

        assert isinstance(result, TabyinContent)
        assert result.external_id == content.external_id

    @pytest.mark.unit
    def test_returns_none_when_inactive(self) -> None:
        content = TabyinContentFactory(is_active=False)

        result = selectors.get_public_content_by_external_id(content.external_id)

        assert result is None

    @pytest.mark.unit
    def test_returns_none_when_deleted_in_source(self) -> None:
        content = TabyinContentFactory(is_deleted_in_source=True)

        result = selectors.get_public_content_by_external_id(content.external_id)

        assert result is None

    @pytest.mark.unit
    def test_returns_none_when_not_found(self) -> None:
        result = selectors.get_public_content_by_external_id("non-existent-id")
        assert result is None


# ============================================================
# Cache — single content detail
# ============================================================


class TestGetPublicContentDetailCached:
    """
    رفتار cache wrapper برای جزئیات یک محتوا.

    این تست‌ها بدون mock کردن backend cache نوشته شده‌اند تا با هر backend
    (locmem یا redis) به‌درستی کار کنند. cache hygiene توسط fixture
    `_clear_cache_between_tests` در conftest.py تضمین می‌شود.
    """

    @pytest.mark.integration
    def test_first_call_hits_db_and_subsequent_call_uses_cache(self) -> None:
        content = TabyinContentFactory(is_active=True, is_deleted_in_source=False)

        # Miss → از DB می‌خواند و در cache می‌گذارد
        first = selectors.get_public_content_detail_cached(content.external_id)
        assert first is not None
        assert first.external_id == content.external_id

        # Hit → دیگر از DB نمی‌خواند، نسخه‌ی cached را برمی‌گرداند
        second = selectors.get_public_content_detail_cached(content.external_id)
        assert second is not None
        assert second.external_id == content.external_id

    @pytest.mark.integration
    def test_returns_none_for_unknown_external_id_without_caching_garbage(
        self,
    ) -> None:
        result_first = selectors.get_public_content_detail_cached("unknown-id")
        result_second = selectors.get_public_content_detail_cached("unknown-id")

        assert result_first is None
        assert result_second is None


# ============================================================
# Cache — paginated list payload
# ============================================================


class TestPublicContentsPageCache:
    """
    رفتار set/get برای cache صفحه‌بندی شده‌ی لیست عمومی.

    این لایه فقط payload خام (dict) را ذخیره می‌کند و تبدیل به serializer
    در سطح بالاتر (view) انجام می‌شود. اینجا فقط round-trip را verify می‌کنیم.
    """

    @pytest.mark.integration
    def test_set_then_get_returns_same_payload(self) -> None:
        payload = {
            "results": [{"external_id": "ext-000001", "title": "hello"}],
            "count": 1,
        }

        selectors.set_public_contents_page_cache(
            page=1,
            page_size=20,
            filters_signature="no_filters",
            payload=payload,
        )

        cached = selectors.get_public_contents_page_cached(
            page=1,
            page_size=20,
            filters_signature="no_filters",
        )

        assert cached == payload

    @pytest.mark.integration
    def test_get_returns_none_when_nothing_cached(self) -> None:
        cached = selectors.get_public_contents_page_cached(
            page=99,
            page_size=20,
            filters_signature="no_filters",
        )
        assert cached is None
