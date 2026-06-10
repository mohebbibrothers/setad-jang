"""
Sandbox payment provider — برای development و تست.

این provider هیچ تماسی با درگاه خارجی برقرار نمی‌کند:
- request_payment: یک authority رندوم تولید می‌کند و یک URL fake برمی‌گرداند.
- verify_payment: همیشه success برمی‌گرداند با ref_id رندوم.

کاربرد:
- development: تست end-to-end flow بدون نیاز به merchant_id واقعی.
- automated tests: قابل پیش‌بینی بودن نتایج.

برای تغییر provider به Zarinpal در production:
    MADADKAR_PAYMENT_PROVIDER=zarinpal

نکات:
- این provider قطعاً نباید در production فعال باشد — settings باید
  حتماً production-grade provider داشته باشد.
- URL برگشتی به کاربر یک صفحه HTML ساده در همان دامنه‌ی پروژه است
  که شبیه‌ساز رفتار درگاه است (در آینده می‌توان view ساده اضافه کرد).
"""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

from .base import (
    AbstractPaymentProvider,
    PaymentRequestResult,
    PaymentVerifyResult,
)

# پیشوند authorityها برای تشخیص ساده sandbox از production در لاگ‌ها
_SANDBOX_AUTHORITY_PREFIX = "SBX-"
_SANDBOX_REF_PREFIX = "SBXREF-"


class SandboxProvider(AbstractPaymentProvider):
    """
    Provider شبیه‌ساز برای dev/test.

    رفتار:
    - request_payment: همیشه success، authority رندوم 32 کاراکتری.
    - verify_payment: همیشه success، verified_amount = amount اصلی.

    این provider برای استفاده در محیط test ایده‌آل است چون deterministic
    و سریع است (بدون network I/O).
    """

    name = "sandbox"

    def request_payment(
        self,
        *,
        amount: int,
        description: str,
        callback_url: str,
        mobile: str = "",
        email: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PaymentRequestResult:
        """ساخت authority رندوم و gateway URL شبیه‌سازی شده."""
        authority = f"{_SANDBOX_AUTHORITY_PREFIX}{secrets.token_urlsafe(24)}"

        # URL به یک endpoint sandbox در همان دامنه ارجاع می‌دهد.
        # کاربر می‌تواند مستقیماً callback_url را با authority فراخوانی کند.
        query = urlencode({"authority": authority, "amount": str(amount)})
        gateway_url = f"{callback_url}?{query}&sandbox=1"

        return PaymentRequestResult(
            success=True,
            authority=authority,
            gateway_url=gateway_url,
            gateway_status="100",
            extra={
                "description": description,
                "mobile": mobile,
                "email": email,
                "metadata": metadata or {},
            },
        )

    def verify_payment(
        self,
        *,
        authority: str,
        amount: int,
    ) -> PaymentVerifyResult:
        """
        تأیید پرداخت sandbox.

        Sandbox همیشه success برمی‌گرداند با مبلغ تأیید شده برابر amount ورودی.
        این یعنی anti-tampering check در سمت service همیشه پاس می‌شود.

        ref_id رندوم تولید می‌شود تا قابل تمایز از authorityها باشد.
        """
        ref_id = f"{_SANDBOX_REF_PREFIX}{secrets.token_urlsafe(20)}"

        return PaymentVerifyResult(
            success=True,
            already_verified=False,
            ref_id=ref_id,
            verified_amount=amount,
            gateway_status="100",
        )
