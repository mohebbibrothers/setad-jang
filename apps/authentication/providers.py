"""
OTP delivery providers.

این ماژول concern مربوط به delivery را از OTP business logic جدا می‌کند.

اهداف معماری:
- OTP service فقط "generate/verify" را بداند، نه "send via what?"
- provider selection قابل‌تغییر از طریق settings باشد
- backward compatibility با تنظیم قدیمی OTP_PROVIDER حفظ شود
- برای future SMS vendor integration فقط یک adapter جدید اضافه شود
- در development بتوانیم بدون پنل SMS واقعی flow را end-to-end تست کنیم

نکته:
- در حال حاضر Email delivery از Django email backend استفاده می‌کند.
- SMS delivery فعلاً از provider کنسولی مخصوص development استفاده می‌کند.
- در production اگر SMS provider واقعی پیکربندی نشده باشد، باید fail loud کند.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Final

import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("apps.authentication")

_CHANNEL_EMAIL: Final[str] = "email"
_CHANNEL_PHONE: Final[str] = "phone"
_LEGACY_PROVIDER_SMS: Final[str] = "sms"

_EMAIL_BACKEND_DJANGO: Final[str] = "django_email"
_SMS_BACKEND_CONSOLE: Final[str] = "console"
_SMS_BACKEND_HTTP: Final[str] = "http"


# ============================================================
# Exceptions
# ============================================================


class OTPDeliveryProviderError(Exception):
    """Base exception برای providerهای ارسال OTP."""


class UnsupportedOTPChannelError(OTPDeliveryProviderError):
    """کانال درخواست‌شده پشتیبانی نمی‌شود."""


class UnsupportedOTPProviderError(OTPDeliveryProviderError):
    """provider backend پیکربندی‌شده نامعتبر است."""


class OTPDeliveryFailedError(OTPDeliveryProviderError):
    """ارسال OTP شکست خورده است."""


# ============================================================
# Base provider
# ============================================================


class OTPDeliveryProvider(ABC):
    """
    قرارداد پایه برای همه‌ی providerهای ارسال OTP.

    هر provider مسئول یک channel مشخص است (مثلاً email یا phone).
    """

    channel: str
    provider_name: str

    @abstractmethod
    def send(self, recipient: str, code: str, purpose: str) -> bool:
        """
        ارسال OTP به recipient موردنظر.

        Returns:
            True اگر ارسال موفق بود.

        Raises:
            OTPDeliveryFailedError:
                اگر provider نتوانست OTP را تحویل دهد.
        """
        raise OTPDeliveryProviderError("Abstract OTP delivery provider cannot send directly.")


# ============================================================
# Email provider
# ============================================================


class EmailOTPProvider(OTPDeliveryProvider):
    """ارسال OTP از طریق Django email backend."""

    channel = _CHANNEL_EMAIL
    provider_name = _EMAIL_BACKEND_DJANGO

    _SUBJECT_MAP: Final[dict[str, str]] = {
        "email_verification": "تأیید ایمیل - ستاد جنگ",
        "password_reset": "بازیابی رمز عبور - ستاد جنگ",
        "login": "کد ورود - ستاد جنگ",
        "signup": "تکمیل ثبت‌نام - ستاد جنگ",
    }

    def _build_subject(self, purpose: str) -> str:
        return self._SUBJECT_MAP.get(purpose, "کد تأیید - ستاد جنگ")

    def _build_message(self, code: str) -> str:
        return (
            f"کد تأیید شما: {code}\n\n"
            "این کد تا ۵ دقیقه اعتبار دارد.\n"
            "در صورتی که شما این درخواست را نداده‌اید، این پیام را نادیده بگیرید."
        )

    def send(self, recipient: str, code: str, purpose: str) -> bool:
        try:
            send_mail(
                subject=self._build_subject(purpose),
                message=self._build_message(code),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception(
                "OTP email delivery failed recipient=%s purpose=%s provider=%s error=%s",
                recipient,
                purpose,
                self.provider_name,
                exc,
            )
            raise OTPDeliveryFailedError("OTP email delivery failed.") from exc

        logger.info(
            "OTP email delivered recipient=%s purpose=%s provider=%s",
            recipient,
            purpose,
            self.provider_name,
        )
        return True


# ============================================================
# SMS console development provider
# ============================================================


class ConsoleSMSOTPProvider(OTPDeliveryProvider):
    """
    Provider کنسولی مخصوص development برای SMS delivery.

    Behavior:
    - در DEBUG: OTP را فقط log می‌کند تا flow قابل تست باشد.
    - در production: fail loud می‌کند تا misconfiguration پنهان نماند.
    """

    channel = _CHANNEL_PHONE
    provider_name = _SMS_BACKEND_CONSOLE

    def send(self, recipient: str, code: str, purpose: str) -> bool:
        if not settings.DEBUG:
            logger.error(
                "SMS OTP provider is not configured for production recipient=%s purpose=%s provider=%s",
                recipient,
                purpose,
                self.provider_name,
            )
            raise OTPDeliveryFailedError(
                "SMS OTP provider is not configured for production.",
            )

        logger.info(
            "[DEV ONLY] OTP SMS console provider recipient=%s purpose=%s code=%s provider=%s",
            recipient,
            purpose,
            code,
            self.provider_name,
        )
        return True


class HTTPAPIOTPProvider(OTPDeliveryProvider):
    """Generic HTTP SMS provider ready for licensed SMS vendors.

    The adapter is intentionally configuration-driven. Many SMS panels accept a
    JSON POST payload with recipient/message/sender and an API token. If a future
    licensed vendor needs a custom shape, a small adapter can be added while the
    OTP service contract remains unchanged.
    """

    channel = _CHANNEL_PHONE
    provider_name = _SMS_BACKEND_HTTP

    def _build_message(self, code: str, purpose: str) -> str:
        """Build a concise SMS body."""
        return f"کد تأیید ستاد جنگ: {code}\nاعتبار: ۵ دقیقه"

    def _build_payload(self, *, recipient: str, code: str, purpose: str) -> dict[str, Any]:
        """Build generic provider payload."""
        return {
            "to": recipient,
            "message": self._build_message(code, purpose),
            "sender": getattr(settings, "SMS_SENDER", ""),
            "purpose": purpose,
        }

    def send(self, recipient: str, code: str, purpose: str) -> bool:
        """Send SMS OTP through a configured HTTP API."""
        api_url = getattr(settings, "SMS_API_URL", "")
        api_key = getattr(settings, "SMS_API_KEY", "")
        timeout = getattr(settings, "SMS_TIMEOUT_SECONDS", 10)
        if not api_url or not api_key:
            raise OTPDeliveryFailedError("SMS HTTP provider is not configured.")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                api_url,
                json=self._build_payload(recipient=recipient, code=code, purpose=purpose),
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            logger.warning("SMS HTTP provider network failure recipient=%s error=%s", recipient, exc)
            raise OTPDeliveryFailedError("SMS HTTP provider request failed.") from exc
        if response.status_code >= 400:
            logger.warning(
                "SMS HTTP provider rejected request recipient=%s status=%s body=%s",
                recipient,
                response.status_code,
                response.text[:200],
            )
            raise OTPDeliveryFailedError("SMS HTTP provider rejected request.")
        logger.info("OTP SMS delivered recipient=%s purpose=%s provider=%s", recipient, purpose, self.provider_name)
        return True


# ============================================================
# Factory helpers
# ============================================================


def _normalize_channel(value: str) -> str:
    """
    نرمال‌سازی channel.

    Compatibility:
    - "email" → "email"
    - "phone" → "phone"
    - "sms"   → "phone"   (legacy compatibility)
    """
    if value == _CHANNEL_EMAIL:
        return _CHANNEL_EMAIL
    if value in {_CHANNEL_PHONE, _LEGACY_PROVIDER_SMS}:
        return _CHANNEL_PHONE

    raise UnsupportedOTPChannelError(f"Unsupported OTP channel: {value}")


def get_email_otp_provider() -> OTPDeliveryProvider:
    """
    ساخت provider مربوط به email.

    از setting آینده‌نگر OTP_EMAIL_PROVIDER استفاده می‌کند، با fallback امن.
    """
    provider_backend = getattr(settings, "OTP_EMAIL_PROVIDER", _EMAIL_BACKEND_DJANGO)

    if provider_backend == _EMAIL_BACKEND_DJANGO:
        return EmailOTPProvider()

    raise UnsupportedOTPProviderError(
        f"Unsupported email OTP provider backend: {provider_backend}",
    )


def get_sms_otp_provider() -> OTPDeliveryProvider:
    """
    ساخت provider مربوط به SMS/phone.

    فعلاً فقط provider کنسولی development پشتیبانی می‌شود.
    """
    provider_backend = getattr(settings, "OTP_SMS_PROVIDER", _SMS_BACKEND_CONSOLE)

    if provider_backend == _SMS_BACKEND_CONSOLE:
        return ConsoleSMSOTPProvider()
    if provider_backend == _SMS_BACKEND_HTTP:
        return HTTPAPIOTPProvider()

    raise UnsupportedOTPProviderError(
        f"Unsupported SMS OTP provider backend: {provider_backend}",
    )


def get_otp_provider(channel: str | None = None) -> OTPDeliveryProvider:
    """
    فکتوری اصلی برای انتخاب provider.

    Modes:
    1. channel-aware (new style):
       get_otp_provider("email")
       get_otp_provider("phone")

    2. legacy fallback:
       get_otp_provider()
       که از setting قدیمی OTP_PROVIDER استفاده می‌کند:
       - "email"
       - "sms"

    این طراحی migration-safe است و اجازه می‌دهد codebase به‌تدریج
    از provider selection قدیمی به channel-aware architecture مهاجرت کند.
    """
    if channel is None:
        channel = getattr(settings, "OTP_PROVIDER", _CHANNEL_EMAIL)

    normalized_channel = _normalize_channel(channel)

    if normalized_channel == _CHANNEL_EMAIL:
        return get_email_otp_provider()

    if normalized_channel == _CHANNEL_PHONE:
        return get_sms_otp_provider()

    raise UnsupportedOTPChannelError(
        f"Unsupported OTP channel after normalization: {normalized_channel}",
    )
