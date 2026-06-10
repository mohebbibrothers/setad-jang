"""
Provider برای سایت محتوانگار (app-service.armansky.ir).

این Provider از MohtavanegarClient برای دریافت داده استفاده می‌کند
و interface استاندارد BaseTabyinProvider را پیاده‌سازی می‌کند.

Logging:
- این ماژول تحت namespace `apps.tabyin.providers.mohtavanegar` لاگ
  می‌گذارد تا با سایر sub-loggerهای `apps.tabyin.*` یکپارچه باشد.
"""

import logging
from typing import Any

from apps.tabyin.providers.base import BaseTabyinProvider
from apps.tabyin.sync.client import MohtavanegarClient
from apps.tabyin.sync.parser import extract_page_info

logger = logging.getLogger("apps.tabyin.providers.mohtavanegar")


class MohtavanegarProvider(BaseTabyinProvider):
    """Provider برای API محتوانگار."""

    def __init__(
        self,
        base_url: str,
        authorization: str,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._client = MohtavanegarClient(
            base_url=base_url,
            authorization=authorization,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._cached_total_pages: int | None = None

    def fetch_page(self, page: int, page_size: int = 30) -> dict[str, Any] | None:
        """دریافت یک صفحه از API محتوانگار."""
        response = self._client.fetch_page(page=page, page_size=page_size)
        if response is None:
            return None

        # کش کردن total_pages از اولین پاسخ
        if self._cached_total_pages is None:
            page_info = extract_page_info(response)
            self._cached_total_pages = page_info["total_pages"]
            logger.info(
                "Source has %d pages, %d total items",
                page_info["total_pages"],
                page_info["total_count"],
            )

        return response

    def fetch_detail(self, content_id: str) -> dict[str, Any] | None:
        """دریافت جزئیات یک محتوا از API محتوانگار."""
        return self._client.fetch_detail(content_id=content_id)

    def get_total_pages(self, page_size: int = 30) -> int:
        """
        تعداد کل صفحات.

        اگر قبلاً fetch نشده، یک درخواست به صفحه ۱ می‌زند.
        """
        if self._cached_total_pages is not None:
            return self._cached_total_pages

        response = self.fetch_page(page=1, page_size=page_size)
        if response is None:
            logger.error("Cannot determine total pages — first page fetch failed")
            return 0

        return self._cached_total_pages or 0

    def close(self) -> None:
        """بستن HTTP client."""
        self._client.close()
