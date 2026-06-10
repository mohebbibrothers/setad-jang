"""
Factory برای ساخت Provider مناسب بر اساس تنظیمات.

مثل provider pattern در اپ authentication.
"""

import logging

from decouple import config

from apps.tabyin.providers.base import BaseTabyinProvider
from apps.tabyin.providers.mohtavanegar import MohtavanegarProvider

logger = logging.getLogger("tabyin.sync")


def get_tabyin_provider() -> BaseTabyinProvider:
    """
    ساخت و بازگرداندن Provider بر اساس تنظیمات .env.

    متغیرهای محیطی:
        TABYIN_PROVIDER: نام provider (پیش‌فرض: mohtavanegar)
        TABYIN_SOURCE_BASE_URL: آدرس پایه API
        TABYIN_SOURCE_AUTH_TOKEN: توکن احراز هویت
        TABYIN_SOURCE_TIMEOUT: timeout درخواست‌ها (ثانیه)
        TABYIN_SOURCE_MAX_RETRIES: حداکثر تلاش مجدد
    """
    provider_name = config("TABYIN_PROVIDER", default="mohtavanegar")

    if provider_name == "mohtavanegar":
        return MohtavanegarProvider(
            base_url=config(
                "TABYIN_SOURCE_BASE_URL",
                default="https://app-service.armansky.ir",
            ),
            authorization=config("TABYIN_SOURCE_AUTH_TOKEN"),
            timeout=config("TABYIN_SOURCE_TIMEOUT", default=30, cast=int),
            max_retries=config("TABYIN_SOURCE_MAX_RETRIES", default=3, cast=int),
        )

    raise ValueError(f"Unknown tabyin provider: {provider_name}")
