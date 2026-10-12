"""
Sandbox payment provider — برای development و تست.

این provider هیچ تماسی با درگاه خارجی برقرار نمی‌کند، اما برخلاف نسخهٔ
اول، رفتار «همیشه موفق» ندارد. دلیلش یک باگ واقعیِ production-adjacent بود:

    gateway_url قبلاً مستقیماً خودِ endpoint verify بود
    ({callback_url}?authority=…&sandbox=1) — یعنی به‌محض «ادامه» در
    فرانت‌اند، مرورگر callback را صدا می‌زد، verify بدون هیچ تعاملی
    success برمی‌گشت و کاربر بدون پرداخت حتی یک ریال «رسید» می‌گرفت.
    هر کلیک دوباره/بوکمارک/اسکنرِ آن URL هم همین کار را می‌کرد.

الان sandbox یک درگاه *تعاملی* است — دقیقاً مثل درگاه واقعی:

1. request_payment → authority رندوم + gateway_url به صفحهٔ شبیه‌ساز
   (/api/v1/madadkar/payment/sandbox/<authority>/) که مبلغ و عنوان
   حرکت را از DB نشان می‌دهد و دو دکمه دارد: «پرداخت را تأیید می‌کنم»
   و «انصراف».
2. کلیک تأیید → ماکر تأیید سمت **سرور** روی رکورد Payment ثبت می‌شود
   (Payment.gateway_status = SANDBOX_CONFIRM_MARKER) و مرورگر با
   Status=OK به callback برمی‌گردد. «انصراف» همان کار را با Status=NOK
   می‌کند (که در view مسیر cancel را می‌رود).
3. verify_payment فقط با مکرِ تأییدِ ثبت‌شده success می‌دهد. یعنی فراخوانی
   مستقیم callback بدون عبور از صفحهٔ درگاه، دیگر هرگز پرداخت را موفق
   علامت نمی‌زند — همان ضدجعل‌سازی که در واقعیت، درگاهِ پرداخت‌نشده را
   تأیید نمی‌کند.

موارد استفاده:
- development: تست end-to-end flow بدون merchant_id واقعی و بدون network.
- automated tests: deterministic — برنامهٔ تست می‌تواند marker را مستقیم
  (بدون مرورگر) ست کند یا از خودِ صفحهٔ شبیه‌ساز عبور کند.

هشدار: این provider هرگز نباید در production فعال باشد؛
config/settings/production.py با RuntimeError از boot جلوی آن را می‌گیرد.
"""

from __future__ import annotations

import secrets
from typing import Any

from django.conf import settings

from .base import (
    AbstractPaymentProvider,
    PaymentRequestResult,
    PaymentVerifyResult,
)

# پیشوند authorityها برای تشخیص ساده sandbox از production در لاگ‌ها
_SANDBOX_AUTHORITY_PREFIX = "SBX-"
_SANDBOX_REF_PREFIX = "SBXREF-"

#: ماکر تأیید سمت سرور. مقدارش در فیلد Payment.gateway_status ذخیره
#: می‌شود (CharField، بدون migration جدید). تنها حالتی که verify_payment
#: success برمی‌گرداند، دیدن همین مقدار روی رکوردِ همان authority است.
#: شبیه‌سازِ «درگاه پول را دید و تأیید کرد».
SANDBOX_CONFIRM_MARKER = "SANDBOX-CONFIRMED"


def build_sandbox_gateway_url(*, authority: str) -> str:
    """URL صفحهٔ شبیه‌ساز درگاه روی همان base که callback ساخته می‌شود.

    دقیقاً همان منبعِ ``views_common._build_callback_url`` استفاده می‌شود
    (settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL) تا اگر base عوض شد،
    صفحهٔ درگاه و callback با هم جابه‌جا شوند.
    """
    base = settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL.rstrip("/")
    return f"{base}/api/v1/madadkar/payment/sandbox/{authority}/"


class SandboxProvider(AbstractPaymentProvider):
    """
    Provider شبیه‌ساز برای dev/test — با تأیید صریح سمت کاربر.

    رفتار:
    - request_payment: همیشه success، authority رندوم، gateway_url
      به صفحهٔ تعاملیِ شبیه‌ساز (نه خودِ callback!).
    - verify_payment: موفق فقط اگر کاربر در صفحهٔ شبیه‌ساز «تأیید» را
      زده باشد (marker روی رکورد Payment). در غیر این صورت
      success=False با پیام راهنما.
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
        """ساخت authority رندوم و URL صفحهٔ شبیه‌سازِ درگاه."""
        authority = f"{_SANDBOX_AUTHORITY_PREFIX}{secrets.token_urlsafe(24)}"

        # برخلاف گذشته، اینجا دیگر callback را با پارامتر نمی‌سازیم —
        # کاربر باید اول صفحهٔ درگاه را ببیند و عمداً «تأیید» را بزند.
        # مبلغ هرگز در URL نمی‌آید؛ صفحهٔ شبیه‌ساز مبلغ را از خودِ
        # رکورد Payment (منبع حقیقت) می‌خواند تا هرگونه تحریف query
        # بی‌اثر بماند.
        gateway_url = build_sandbox_gateway_url(authority=authority)

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
        تأیید پرداخت sandbox — مشروط به تأیید صریح کاربر در صفحهٔ درگاه.

        marker («SANDBOX-CONFIRMED») هنگام کلیک دکمهٔ تأیید روی همان
        رکوردِ Payment نوشته می‌شود؛ verify بدون آن، همان کاری را می‌کند
        که زرین‌پال با یک authority پرداخت‌نشود می‌کند: success=False.
        verified_amount برابر amount ورودی است (مبلغِ خودِ رکورد، که
        service از DB می‌خواند) — پس anti-tampering check معنادار باقی
        می‌ماند.
        """
        from apps.madadkar.models import Payment

        marker = (
            Payment.objects.filter(authority=authority, gateway_name=self.name)
            .values_list("gateway_status", flat=True)
            .first()
        )

        if marker != SANDBOX_CONFIRM_MARKER:
            return PaymentVerifyResult(
                success=False,
                error_message=(
                    "پرداخت sandbox هنوز توسط کاربر در صفحهٔ درگاهِ آزمایشی تأیید نشده است. "
                    "برای شبیه‌سازی پرداخت موفق، ابتدا باید gateway_url باز شده و دکمهٔ "
                    "«تأیید پرداخت» زده شود."
                ),
            )

        ref_id = f"{_SANDBOX_REF_PREFIX}{secrets.token_urlsafe(20)}"

        return PaymentVerifyResult(
            success=True,
            already_verified=False,
            ref_id=ref_id,
            verified_amount=amount,
            gateway_status="100",
        )

    def initiate_refund(self, *, authority: str, amount: int, reason: str = "") -> bool:
        """Refund در sandbox همیشه موفق است (هیچ پول واقعی جابه‌جا نشده)."""
        return True
