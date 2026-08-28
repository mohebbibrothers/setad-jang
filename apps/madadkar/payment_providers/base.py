"""
Abstract payment provider interface.

این ماژول contract یکپارچه‌ای برای تمام درگاه‌های پرداخت تعریف می‌کند.
هر provider جدید (Zarinpal, IDPay, Mellat, ...) فقط باید این ABC را
implement کند و در factory ثبت شود.

اصول طراحی:
- Provider هیچ DB write مستقیمی انجام نمی‌دهد — فقط با درگاه خارجی صحبت می‌کند.
- نتایج به‌صورت dataclasses immutable برگردانده می‌شوند برای type safety.
- خطاهای provider به‌صورت structured (با code + message) منتقل می‌شوند.
- request_payment idempotent نیست (هر بار authority جدید می‌سازد).
- verify_payment باید **در سمت provider** idempotent باشد — این رفتار
  در سمت ما هم با چک کردن status قبل از فراخوانی provider تضمین می‌شود.

نکات امنیتی critical:
- amount در verify_payment به provider ارسال می‌شود تا با مقدار stored
  در گیت‌وی مقایسه شود (anti-tampering).
- اگر provider مقدار متفاوت برگرداند، service باید verify را reject کند.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentRequestResult:
    """
    نتیجه فراخوانی request_payment.

    Attributes:
        success: آیا درخواست به درگاه موفق بود؟ (نه پرداخت موفق — فقط درخواست!)
        authority: کد یکتایی که توسط درگاه تولید می‌شود برای پیگیری.
        gateway_url: URL کاملی که کاربر باید به آن redirect شود.
        gateway_status: کد وضعیت خام درگاه (برای logging).
        error_message: پیام خطا در صورت ناموفق بودن.
        extra: داده‌های اضافی provider-specific (اختیاری).
    """

    success: bool
    authority: str = ""
    gateway_url: str = ""
    gateway_status: str = ""
    error_message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentVerifyResult:
    """
    نتیجه فراخوانی verify_payment.

    Attributes:
        success: آیا پرداخت تأیید شد و معتبر است؟
        already_verified: آیا این تراکنش قبلاً verify شده بود؟ (idempotency)
        ref_id: شناسه نهایی پرداخت در درگاه (برای نمایش به کاربر).
        verified_amount: مبلغی که درگاه تأیید کرده — باید با amount ما برابر باشد.
        gateway_status: کد وضعیت خام درگاه (برای logging).
        error_message: پیام خطا در صورت ناموفق بودن.
        extra: داده‌های اضافی provider-specific (اختیاری).
    """

    success: bool
    already_verified: bool = False
    ref_id: str = ""
    verified_amount: int = 0
    gateway_status: str = ""
    error_message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


class AbstractPaymentProvider(ABC):
    """
    Interface پایه برای تمام درگاه‌های پرداخت.

    Implementations:
    - SandboxProvider: برای dev/test (همیشه success)
    - ZarinpalProvider: production-ready HTTP integration
    - IDPayProvider, MellatProvider, ... (آینده)

    قراردادها:
    - name باید unique و lowercase باشد (e.g. "sandbox", "zarinpal").
    - تمام I/O با درگاه باید timeout داشته باشد.
    - exception نباید leak شود — هر خطا را در PaymentRequestResult/PaymentVerifyResult
      با success=False و error_message برگردانید.
    """

    #: نام شناسایی provider — در DB در فیلد Payment.gateway_name ذخیره می‌شود.
    name: str = ""

    @abstractmethod
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
        ارسال درخواست پرداخت به درگاه.

        Args:
            amount: مبلغ به تومان.
            description: توضیحات قابل نمایش به کاربر در صفحه درگاه.
            callback_url: URL کاملی که درگاه بعد از پرداخت به آن redirect می‌کند.
            mobile: شماره موبایل کاربر (اختیاری — برخی درگاه‌ها استفاده می‌کنند).
            email: ایمیل کاربر (اختیاری).
            metadata: داده‌های اضافی provider-specific (مثل order_id).

        Returns:
            PaymentRequestResult با authority و gateway_url در صورت موفقیت.
        """

    @abstractmethod
    def verify_payment(
        self,
        *,
        authority: str,
        amount: int,
    ) -> PaymentVerifyResult:
        """
        تأیید نهایی پرداخت با درگاه.

        Args:
            authority: کد رهگیری که از request_payment دریافت شده.
            amount: مبلغ original — باید با مقدار درگاه تطبیق داده شود.

        Returns:
            PaymentVerifyResult با ref_id و verified_amount در صورت موفقیت.
        """
