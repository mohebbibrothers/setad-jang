"""
Payment providers factory.

این ماژول factory function اصلی `get_payment_provider()` را export می‌کند
که بر اساس `settings.MADADKAR_PAYMENT_PROVIDER` نمونه‌ی provider مناسب
را برمی‌گرداند.

اصول طراحی:
- Single source of truth: تغییر provider فقط از طریق settings.
- Late binding: provider instance در زمان فراخوانی ساخته می‌شود (نه import time).
- Type-safe: نتیجه همیشه AbstractPaymentProvider است.
- Extensible: اضافه کردن provider جدید فقط با ثبت در `_PROVIDER_REGISTRY`.

Usage:
    from apps.madadkar.payment_providers import get_payment_provider

    provider = get_payment_provider()
    result = provider.request_payment(amount=50_000_000, ...)
"""

from __future__ import annotations

import logging
from typing import Final

from django.conf import settings

from .base import (
    AbstractPaymentProvider,
    PaymentRequestResult,
    PaymentVerifyResult,
)
from .sandbox import SandboxProvider
from .zarinpal import ZarinpalNotConfiguredError, ZarinpalProvider

logger = logging.getLogger("apps.madadkar")

# Registry — برای اضافه کردن provider جدید، فقط اینجا ثبت کنید
_PROVIDER_REGISTRY: Final[dict[str, type[AbstractPaymentProvider]]] = {
    SandboxProvider.name: SandboxProvider,
    ZarinpalProvider.name: ZarinpalProvider,
}


class UnknownPaymentProviderError(RuntimeError):
    """نام provider مشخص‌شده در settings در registry یافت نشد."""


def get_payment_provider(name: str | None = None) -> AbstractPaymentProvider:
    """
    دریافت نمونه provider بر اساس name یا settings.

    Args:
        name: نام provider (اختیاری). اگر None باشد از
              `settings.MADADKAR_PAYMENT_PROVIDER` استفاده می‌شود.

    Returns:
        نمونه ساخته‌شده از AbstractPaymentProvider.

    Raises:
        UnknownPaymentProviderError: اگر name در registry نباشد.
        ZarinpalNotConfiguredError: اگر zarinpal انتخاب شده اما
            MADADKAR_ZARINPAL_MERCHANT_ID مقداردهی نشده باشد.
    """
    provider_name = (name or settings.MADADKAR_PAYMENT_PROVIDER).strip().lower()

    provider_cls = _PROVIDER_REGISTRY.get(provider_name)
    if provider_cls is None:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        msg = (
            f"Payment provider '{provider_name}' یافت نشد. "
            f"providerهای موجود: {available}"
        )
        raise UnknownPaymentProviderError(msg)

    provider = provider_cls()
    logger.debug(
        "Madadkar payment provider resolved provider=%s class=%s",
        provider_name,
        provider_cls.__name__,
    )
    return provider


__all__ = [
    "AbstractPaymentProvider",
    "PaymentRequestResult",
    "PaymentVerifyResult",
    "SandboxProvider",
    "UnknownPaymentProviderError",
    "ZarinpalNotConfiguredError",
    "ZarinpalProvider",
    "get_payment_provider",
]
