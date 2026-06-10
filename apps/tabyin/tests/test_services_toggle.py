"""
Tests — apps.tabyin.services.toggle_content_visibility

این تست‌ها دو رفتار حیاتی toggle را verify می‌کنند:

1. تغییر state واقعی روی DB:
   - فعال‌سازی محتوای غیرفعال
   - غیرفعال‌سازی محتوای فعال
   - idempotent بودن (toggle با همان مقدار state نباید رفتار را خراب کند)

2. invalidation کامل cache عمومی پس از mutation:
   - بعد از toggle، نه get_public_content_detail_cached و نه page-cache
     نباید مقدار قدیمی برگردانند.

اصول طراحی تست‌ها:
- بدون mock کردن backend cache نوشته می‌شوند تا با هر backend سازگار باشند.
- داده فقط از طریق factory-boy ساخته می‌شود.
- تست‌ها deterministic و مستقل از زمان هستند.
- cache hygiene توسط fixture `_clear_cache_between_tests` در conftest.py
  در ابتدا و انتهای هر تست انجام می‌شود.
"""

from __future__ import annotations

import pytest

from apps.tabyin import selectors, services
from tests.factories import TabyinContentFactory

pytestmark = [pytest.mark.django_db]


# ============================================================
# State transitions
# ============================================================


class TestToggleContentVisibilityState:
    """رفتار تغییر فیلد is_active در سطح DB."""

    @pytest.mark.unit
    def test_activates_inactive_content(self) -> None:
        content = TabyinContentFactory(is_active=False)

        result = services.toggle_content_visibility(
            content=content,
            is_active=True,
        )

        result.refresh_from_db()
        assert result.is_active is True

    @pytest.mark.unit
    def test_deactivates_active_content(self) -> None:
        content = TabyinContentFactory(is_active=True)

        result = services.toggle_content_visibility(
            content=content,
            is_active=False,
        )

        result.refresh_from_db()
        assert result.is_active is False

    @pytest.mark.unit
    def test_is_idempotent_when_value_does_not_change(self) -> None:
        content = TabyinContentFactory(is_active=True)

        result = services.toggle_content_visibility(
            content=content,
            is_active=True,
        )

        result.refresh_from_db()
        assert result.is_active is True


# ============================================================
# Cache invalidation
# ============================================================


class TestToggleContentVisibilityCacheInvalidation:
    """
    بعد از تغییر state، cacheهای عمومی نباید مقدار قدیمی برگردانند.
    """

    @pytest.mark.integration
    def test_detail_cache_is_invalidated_after_deactivation(self) -> None:
        content = TabyinContentFactory(is_active=True, is_deleted_in_source=False)

        # Pre-warm: cache باید پر شود
        warm = selectors.get_public_content_detail_cached(content.external_id)
        assert warm is not None
        assert warm.external_id == content.external_id

        # Mutation: غیرفعال کردن باید cache را invalidate کند
        services.toggle_content_visibility(content=content, is_active=False)

        # Post-state: محتوا دیگر نباید عمومی برگردد
        after = selectors.get_public_content_detail_cached(content.external_id)
        assert after is None

    @pytest.mark.integration
    def test_detail_cache_is_invalidated_after_reactivation(self) -> None:
        content = TabyinContentFactory(is_active=False, is_deleted_in_source=False)

        # Pre-warm: چون غیرفعال است، cache هم None برمی‌گرداند
        warm = selectors.get_public_content_detail_cached(content.external_id)
        assert warm is None

        # Mutation: فعال‌سازی باید cache (با نتیجه‌ی negative) را invalidate کند
        services.toggle_content_visibility(content=content, is_active=True)

        # Post-state: حالا باید عمومی شود
        after = selectors.get_public_content_detail_cached(content.external_id)
        assert after is not None
        assert after.external_id == content.external_id

    @pytest.mark.integration
    def test_list_page_cache_is_invalidated_after_toggle(self) -> None:
        content = TabyinContentFactory(is_active=True, is_deleted_in_source=False)

        # Pre-warm: payload دلخواه‌ای را به‌عنوان نسخه‌ی قبلی cache می‌کنیم
        previous_payload = {
            "results": [{"external_id": content.external_id, "title": "old"}],
            "count": 1,
        }
        selectors.set_public_contents_page_cache(
            page=1,
            page_size=20,
            filters_signature="no_filters",
            payload=previous_payload,
        )

        # تأیید اینکه pre-warm درست انجام شده
        warm = selectors.get_public_contents_page_cached(
            page=1,
            page_size=20,
            filters_signature="no_filters",
        )
        assert warm == previous_payload

        # Mutation: toggle باید namespace lib_list را پاک کند
        services.toggle_content_visibility(content=content, is_active=False)

        # Post-state: cache صفحه باید invalid شده باشد
        after = selectors.get_public_contents_page_cached(
            page=1,
            page_size=20,
            filters_signature="no_filters",
        )
        assert after is None
