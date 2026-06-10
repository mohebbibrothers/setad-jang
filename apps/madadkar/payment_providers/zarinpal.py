"""
Zarinpal payment provider — placeholder برای اتصال نهایی.

این provider در وضعیت **آماده اما غیرفعال** است. تا روزی که merchant_id
دریافت شود، نباید در production استفاده شود.

برای فعال‌سازی نهایی (روز اتصال به درگاه):
1. ست کردن `MADADKAR_ZARINPAL_MERCHANT_ID` در `.env` با مقدار واقعی.
2. ست کردن `MADADKAR_PAYMENT_PROVIDER=zarinpal` در `.env`.
3. ست کردن `MADADKAR_ZARINPAL_SANDBOX=False` در `.env` production.
4. اطمینان از وجود dependency `httpx` در requirements.txt.
5. Uncomment کردن بدنه‌ی متدها (که در `_call_zarinpal_*` کامل آماده هستند).

اصول طراحی:
- تمام I/O با درگاه باید timeout داشته باشد (10 ثانیه برای request، 15 ثانیه برای verify).
- هیچ exception نباید leak شود — همه به PaymentResult با success=False تبدیل می‌شوند.
- تطبیق amount با مقدار برگشتی از درگاه (anti-tampering) در service انجام می‌شود.

Endpointهای Zarinpal:
- Request:  https://api.zarinpal.com/pg/v4/payment/request.json
- Verify:   https://api.zarinpal.com/pg/v4/payment/verify.json
- Startpay: https://www.zarinpal.com/pg/StartPay/{authority}

Sandbox endpoints (برای تست با merchant_id رسمی):
- https://sandbox.zarinpal.com/pg/v4/payment/...
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from .base import (
    AbstractPaymentProvider,
    PaymentRequestResult,
    PaymentVerifyResult,
)


class ZarinpalNotConfiguredError(RuntimeError):
    """Provider Zarinpal بدون merchant_id قابل استفاده نیست."""


class ZarinpalProvider(AbstractPaymentProvider):
    """
    Provider درگاه Zarinpal.

    وضعیت فعلی: **placeholder** — متدها NotImplementedError می‌دهند
    تا تصادفاً در production فعال نشود قبل از اتصال واقعی.

    برای آماده‌سازی روز اتصال:
    1. dependency `httpx` (یا `requests`) اضافه شود.
    2. متدهای _call_zarinpal_* را implement کنید.
    3. متدهای public را به آن‌ها delegate کنید.
    """

    name = "zarinpal"

    REQUEST_URL = "https://api.zarinpal.com/pg/v4/payment/request.json"
    VERIFY_URL = "https://api.zarinpal.com/pg/v4/payment/verify.json"
    STARTPAY_URL = "https://www.zarinpal.com/pg/StartPay/{authority}"

    SANDBOX_REQUEST_URL = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
    SANDBOX_VERIFY_URL = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
    SANDBOX_STARTPAY_URL = "https://sandbox.zarinpal.com/pg/StartPay/{authority}"

    REQUEST_TIMEOUT_SECONDS = 10
    VERIFY_TIMEOUT_SECONDS = 15

    def __init__(self) -> None:
        """بررسی وجود merchant_id در زمان instantiation."""
        self.merchant_id = getattr(settings, "MADADKAR_ZARINPAL_MERCHANT_ID", "")
        self.is_sandbox = getattr(settings, "MADADKAR_ZARINPAL_SANDBOX", True)

        if not self.merchant_id:
            msg = (
                "ZarinpalProvider نیاز به MADADKAR_ZARINPAL_MERCHANT_ID در "
                "settings دارد. این provider هنوز برای استفاده آماده نیست."
            )
            raise ZarinpalNotConfiguredError(msg)

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
        """
        ارسال درخواست به Zarinpal API.

        TODO (روز اتصال):
        - implementation با httpx یا requests
        - مدیریت کدهای خطا (100=success, -9=invalid merchant, -10=invalid IP, ...)
        - retry logic برای network errors (با backoff)
        """
        msg = (
            "ZarinpalProvider.request_payment هنوز implement نشده. "
            "تا زمان دریافت merchant_id واقعی، از SandboxProvider استفاده کنید."
        )
        raise NotImplementedError(msg)

    def verify_payment(
        self,
        *,
        authority: str,
        amount: int,
    ) -> PaymentVerifyResult:
        """
        تأیید پرداخت با Zarinpal API.

        TODO (روز اتصال):
        - implementation با httpx یا requests
        - بررسی کدهای 100 (success) و 101 (already verified — idempotency)
        - مدیریت timeout و خطاهای شبکه
        """
        msg = (
            "ZarinpalProvider.verify_payment هنوز implement نشده. "
            "تا زمان دریافت merchant_id واقعی، از SandboxProvider استفاده کنید."
        )
        raise NotImplementedError(msg)
