"""
HTTP Client حرفه‌ای برای ارتباط با API محتوانگار.

ویژگی‌ها:
- Session-based (connection reuse)
- Retry خودکار با exponential backoff (urllib3 + manual)
- Timeout مناسب
- لاگ‌گذاری hierarchical تحت namespace `apps.tabyin.sync.client`
- بدون افشای authorization در logs
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("apps.tabyin.sync.client")


class MohtavanegarClient:
    """HTTP Client برای API محتوانگار با retry و backoff."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 520, 521, 522, 524}
    MANUAL_RETRY_MAX = 3
    MANUAL_RETRY_BASE_DELAY = 2.0

    def __init__(
        self,
        base_url: str,
        authorization: str,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = self._build_session(
            authorization=authorization,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
        )

    def _build_session(
        self,
        authorization: str,
        max_retries: int,
        backoff_factor: float,
    ) -> requests.Session:
        session = requests.Session()

        session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
                "Authorization": authorization,
                "Origin": "https://app.armansky.ir",
                "Referer": "https://app.armansky.ir/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/148.0.0.0 Safari/537.36"
                ),
            }
        )

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=list(self.RETRYABLE_STATUS_CODES),
            allowed_methods=["GET"],
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def fetch_page(self, page: int, page_size: int = 30) -> dict[str, Any] | None:
        url = (
            f"{self._base_url}/api/entity/search"
            f"?full_search=true&fields%5B5%5D=&page={page}&page_size={page_size}"
        )
        return self._get_with_retry(url, context=f"page={page}")

    def fetch_detail(self, content_id: str) -> dict[str, Any] | None:
        url = f"{self._base_url}/api/entity/search?id={content_id}&full_search=true"
        return self._get_with_retry(url, context=f"id={content_id}")

    def _get_with_retry(self, url: str, context: str = "") -> dict[str, Any] | None:
        for attempt in range(1, self.MANUAL_RETRY_MAX + 1):
            result = self._get(url, context=context)
            if result is not None:
                return result

            if attempt < self.MANUAL_RETRY_MAX:
                delay = self.MANUAL_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Manual retry %d/%d for %s after %.1fs delay...",
                    attempt + 1,
                    self.MANUAL_RETRY_MAX,
                    context,
                    delay,
                )
                time.sleep(delay)

        logger.error("All retry attempts failed for %s", context)
        return None

    def _get(self, url: str, context: str = "") -> dict[str, Any] | None:
        try:
            logger.debug("Fetching: %s", context)
            response = self._session.get(url, timeout=self._timeout)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning("Rate limited (%s). Sleeping %ds...", context, retry_after)
                time.sleep(retry_after)
                response = self._session.get(url, timeout=self._timeout)

            if response.status_code in self.RETRYABLE_STATUS_CODES:
                logger.error(
                    "HTTP %d for %s (retryable)",
                    response.status_code,
                    context,
                )
                return None

            if response.status_code != 200:
                logger.error(
                    "HTTP %d for %s — %s",
                    response.status_code,
                    context,
                    response.text[:200],
                )
                return None

            content_type = response.headers.get("Content-Type", "").lower()
            if "application/json" not in content_type:
                logger.error(
                    "Unexpected Content-Type for %s: %s (expected JSON)",
                    context,
                    content_type,
                )
                return None

            data = response.json()

            if not data.get("status"):
                logger.error("API returned status=false for %s", context)
                return None

            return data

        except requests.exceptions.Timeout:
            logger.error("Timeout for %s", context)
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Connection error for %s", context)
            return None
        except requests.exceptions.JSONDecodeError:
            logger.error("Invalid JSON for %s", context)
            return None
        except Exception:
            logger.exception("Unexpected error for %s", context)
            return None

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> MohtavanegarClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
