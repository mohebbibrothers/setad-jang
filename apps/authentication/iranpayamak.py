"""IranPayamak pattern-based SMS delivery provider for OTP.

قرارداد الگوی پیامکی (Pattern):
- متن پیامک در ایران‌پیامک باید از پیش به‌صورت «الگو» ثبت و تأیید شود؛ API تنها
  کد الگو + مقادیر placeholder را می‌گیرد. به همین دلیل هر purpose ورودی
  `OTPPurpose` نقشه‌ی جداگانه به کد الگو دارد (تنظیمات SMS_IRANPAYAMAK_PATTERN_*).
- کد الگو و شماره خط سرویس راز نیستند ولی خروجیِ پنل هر محیط‌اند؛ پس در `.env`
  می‌آیند، نه در کد. تنها `SMS_IRANPAYAMAK_API_KEY` راز است و هرگز commit
  نمی‌شود.
- شمارهٔ مقصد داخلی E.164 است (+98...) ولی درگاه فرمت ملی (09...) می‌خواهد؛
  نرمال‌سازی همین‌جا انجام می‌شود.
- هر پاسخِ غیرموفق باید `OTPDeliveryFailedError` بدهد تا service لایهٔ OTP
  رکورد تعلیقی را rollback کند (OTP یتیم ساخته نشود).

اسناد: https://docs.iranpayamak.com — «Send Pattern-Based SMS»
پاسخ موفق: HTTP 201 با بدنهٔ {"status": "success", ...}
"""

from __future__ import annotations

import logging
import re
from typing import Any, Final

import requests
from django.conf import settings

from .choices import OTPPurpose
from .logging_utils import mask_identifier
from .providers import OTPDeliveryFailedError, OTPDeliveryProvider

logger = logging.getLogger("apps.authentication")

DEFAULT_PATTERN_URL: Final[str] = "https://api.iranpayamak.com/ws/v1/sms/pattern"

#: پاسخ‌های HTTP موفقِ سند رسمی (201 مستند شده؛ 200 برای سازگاری tolerat می‌شود).
_SUCCESS_HTTP_STATUSES: Final[frozenset[int]] = frozenset({200, 201})

#: الگوی شمارهٔ موبایل ایران در فرمت ملی که درگاه انتظار دارد.
_IR_MOBILE_RE: Final[re.Pattern[str]] = re.compile(r"^09\d{9}$")


class IranPayamakOTPProvider(OTPDeliveryProvider):
    """ارسال OTP پیامکی با الگوی تأییدشده از طریق API ایران‌پیامک."""

    channel = "phone"
    provider_name = "iranpayamak"

    def __init__(self) -> None:
        self.api_key: str = getattr(settings, "SMS_IRANPAYAMAK_API_KEY", "") or ""
        self.pattern_url: str = (
            getattr(settings, "SMS_IRANPAYAMAK_PATTERN_URL", DEFAULT_PATTERN_URL)
            or DEFAULT_PATTERN_URL
        )
        self.line_number: str = getattr(settings, "SMS_IRANPAYAMAK_LINE_NUMBER", "") or ""
        self.number_format: str = (
            getattr(settings, "SMS_IRANPAYAMAK_NUMBER_FORMAT", "persian") or ""
        )
        self.timeout_seconds: int = int(getattr(settings, "SMS_IRANPAYAMAK_TIMEOUT_SECONDS", 10))
        self.pattern_codes: dict[str, str] = {
            OTPPurpose.LOGIN.value: getattr(settings, "SMS_IRANPAYAMAK_PATTERN_LOGIN", "") or "",
            OTPPurpose.SIGNUP.value: getattr(settings, "SMS_IRANPAYAMAK_PATTERN_SIGNUP", "") or "",
            OTPPurpose.PASSWORD_RESET.value: getattr(
                settings, "SMS_IRANPAYAMAK_PATTERN_PASSWORD_RESET", ""
            )
            or "",
            OTPPurpose.IDENTIFIER_ADD.value: getattr(
                settings, "SMS_IRANPAYAMAK_PATTERN_IDENTIFIER_ADD", ""
            )
            or "",
        }

    @staticmethod
    def _normalize_recipient(recipient: str) -> str:
        """تبدیل شماره از فرمت‌های مرسوم (+98/0098/98) به فرمت ملی 09xxxxxxxxx.

        خروجی حتماً با `09` شروع و ۱۱ رقمی است؛ در غیر این صورت fail loud —
        ارسال شمارهٔ نیمه‌ساز به درگاه بی‌معناست و فقط credit مصرف می‌کند.
        """
        value = re.sub(r"[\s\-()]", "", recipient or "")
        if value.startswith("+"):
            value = value[1:]
        if value.startswith("0098"):
            value = "0" + value[4:]
        elif value.startswith("98") and len(value) == 12:
            value = "0" + value[2:]
        if not _IR_MOBILE_RE.fullmatch(value):
            raise OTPDeliveryFailedError("شمارهٔ مقصد برای ارسال پیامک اعتبارسنجی نشد.")
        return value

    def _build_payload(self, *, pattern_code: str, recipient: str, code: str) -> dict[str, Any]:
        """ساخت payload مطابق سند «Send Pattern-Based SMS»."""
        payload: dict[str, Any] = {
            "code": pattern_code,
            # placeholder متن الگو دقیقاً «code» است (تأییدشده در پنل).
            "attributes": {"code": code},
            "recipient": self._normalize_recipient(recipient),
        }
        if self.line_number:
            payload["line_number"] = self.line_number
        if self.number_format:
            payload["number_format"] = self.number_format
        return payload

    @staticmethod
    def _extract_vendor_message(body: dict[str, Any], raw_text: str) -> str:
        """پیام خطای ایران‌پیامک (تک/چندتایی) با fallback به متن خام."""
        message = body.get("messages") or body.get("message") or ""
        if isinstance(message, (list, tuple)):
            message = "; ".join(str(item) for item in message)
        return str(message).strip() or raw_text[:200]

    def send(self, recipient: str, code: str, purpose: str) -> bool:
        """ارسال OTP با الگوی مربوط به purpose.

        Raises:
            OTPDeliveryFailedError: تنظیمات ناقص، شمارهٔ نامعتبر، خطای شبکه یا
                هر پاسخ غیر success از سمت درگاه.
        """
        if not self.api_key:
            raise OTPDeliveryFailedError(
                "IranPayamak API key is not configured (SMS_IRANPAYAMAK_API_KEY)."
            )
        pattern_code = self.pattern_codes.get(purpose, "")
        if not pattern_code:
            raise OTPDeliveryFailedError(
                f"No SMS pattern code configured for OTP purpose '{purpose}'."
            )

        payload = self._build_payload(pattern_code=pattern_code, recipient=recipient, code=code)
        try:
            response = requests.post(
                self.pattern_url,
                json=payload,
                headers={"Api-Key": self.api_key, "Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            logger.warning("IranPayamak SMS transport failure purpose=%s error=%s", purpose, exc)
            raise OTPDeliveryFailedError("IranPayamak SMS request failed.") from exc

        body: dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = {}

        vendor_status = str(body.get("status", "")).lower()
        if response.status_code not in _SUCCESS_HTTP_STATUSES or vendor_status != "success":
            detail = self._extract_vendor_message(body, response.text)
            logger.warning(
                "IranPayamak rejected SMS recipient=%s purpose=%s pattern=%s http=%s vendor=%s detail=%s",
                mask_identifier(recipient, identifier_kind="phone"),
                purpose,
                pattern_code,
                response.status_code,
                vendor_status,
                detail,
            )
            raise OTPDeliveryFailedError("IranPayamak SMS was not accepted by the vendor.")

        logger.info(
            "OTP SMS delivered recipient=%s purpose=%s provider=%s",
            mask_identifier(recipient, identifier_kind="phone"),
            purpose,
            self.provider_name,
        )
        return True
