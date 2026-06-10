"""
Zarinpal payment provider.

این provider اتصال واقعی به API پرداخت زرین‌پال را پشت contract مشترک
`AbstractPaymentProvider` پیاده‌سازی می‌کند تا service layer مددکار هیچ وابستگی
مستقیمی به جزئیات HTTP، endpointها، کدهای وضعیت یا قالب پاسخ زرین‌پال نداشته
باشد.

اصول طراحی:
- تمام I/O با timeout محدود اجرا می‌شود.
- هیچ exception شبکه‌ای یا parse-level به service layer leak نمی‌شود.
- پاسخ‌های موفق/ناموفق همیشه به dataclassهای استاندارد تبدیل می‌شوند.
- کد 100 به‌عنوان success و کد 101 در verify به‌عنوان already verified
  و idempotent success در نظر گرفته می‌شود.
- تطبیق مبلغ نهایی همچنان در service انجام می‌شود؛ provider مبلغ ورودی را
  به‌عنوان `verified_amount` برمی‌گرداند چون API زرین‌پال در verify مبلغ
  جداگانه‌ای در response استاندارد برنمی‌گرداند و خودش amount ارسالی را
  validate می‌کند.

Endpointهای production:
- Request:  https://api.zarinpal.com/pg/v4/payment/request.json
- Verify:   https://api.zarinpal.com/pg/v4/payment/verify.json
- StartPay: https://www.zarinpal.com/pg/StartPay/{authority}

Endpointهای sandbox:
- Request:  https://sandbox.zarinpal.com/pg/v4/payment/request.json
- Verify:   https://sandbox.zarinpal.com/pg/v4/payment/verify.json
- StartPay: https://sandbox.zarinpal.com/pg/StartPay/{authority}
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

from .base import (
    AbstractPaymentProvider,
    PaymentRequestResult,
    PaymentVerifyResult,
)

logger = logging.getLogger("apps.madadkar")


class ZarinpalNotConfiguredError(RuntimeError):
    """Provider Zarinpal بدون merchant_id قابل استفاده نیست."""


class ZarinpalProvider(AbstractPaymentProvider):
    """
    Provider درگاه Zarinpal.

    این کلاس فقط مسئول ارتباط با زرین‌پال است. DB write، state transition،
    audit logging، idempotency سطح domain و amount-tampering protection در
    `apps.madadkar.services` باقی می‌مانند.
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
    SUCCESS_CODE = "100"
    ALREADY_VERIFIED_CODE = "101"

    def __init__(self) -> None:
        """خواندن و validate کردن تنظیمات لازم در زمان ساخت provider."""
        self.merchant_id = getattr(settings, "MADADKAR_ZARINPAL_MERCHANT_ID", "")
        self.is_sandbox = getattr(settings, "MADADKAR_ZARINPAL_SANDBOX", True)

        if not self.merchant_id:
            msg = (
                "ZarinpalProvider نیاز به MADADKAR_ZARINPAL_MERCHANT_ID در "
                "settings دارد."
            )
            raise ZarinpalNotConfiguredError(msg)

    @property
    def request_url(self) -> str:
        """URL مناسب request_payment بر اساس sandbox/production بودن provider."""
        return self.SANDBOX_REQUEST_URL if self.is_sandbox else self.REQUEST_URL

    @property
    def verify_url(self) -> str:
        """URL مناسب verify_payment بر اساس sandbox/production بودن provider."""
        return self.SANDBOX_VERIFY_URL if self.is_sandbox else self.VERIFY_URL

    @property
    def startpay_url_template(self) -> str:
        """قالب URL redirect کاربر به صفحه پرداخت زرین‌پال."""
        return self.SANDBOX_STARTPAY_URL if self.is_sandbox else self.STARTPAY_URL

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
        ارسال درخواست ایجاد تراکنش به زرین‌پال.

        Args:
            amount: مبلغ به تومان، مطابق قرارداد داخلی پروژه.
            description: توضیح قابل نمایش در درگاه.
            callback_url: URL بازگشت بعد از پرداخت.
            mobile: شماره موبایل کاربر، در صورت وجود.
            email: ایمیل کاربر، در صورت وجود.
            metadata: metadata تکمیلی provider-specific.

        Returns:
            PaymentRequestResult استاندارد با authority و gateway_url در حالت موفق.
        """
        payload: dict[str, Any] = {
            "merchant_id": self.merchant_id,
            "amount": amount,
            "description": description,
            "callback_url": callback_url,
        }
        request_metadata = self._build_request_metadata(
            mobile=mobile,
            email=email,
            metadata=metadata,
        )
        if request_metadata:
            payload["metadata"] = request_metadata

        response_payload, transport_error = self._post_json(
            url=self.request_url,
            payload=payload,
            timeout=self.REQUEST_TIMEOUT_SECONDS,
            operation="request_payment",
        )
        if transport_error:
            return PaymentRequestResult(
                success=False,
                gateway_status="transport_error",
                error_message=transport_error,
            )

        data = self._extract_data(response_payload)
        code = self._extract_code(data)
        authority = str(data.get("authority") or "")

        if code == self.SUCCESS_CODE and authority:
            logger.info(
                "Zarinpal request_payment succeeded authority=%s amount=%s sandbox=%s",
                authority,
                amount,
                self.is_sandbox,
            )
            return PaymentRequestResult(
                success=True,
                authority=authority,
                gateway_url=self.startpay_url_template.format(authority=authority),
                gateway_status=code,
                extra={"raw_data": data},
            )

        error_message = self._extract_error_message(response_payload)
        logger.warning(
            "Zarinpal request_payment failed status=%s amount=%s error=%s",
            code,
            amount,
            error_message,
        )
        return PaymentRequestResult(
            success=False,
            gateway_status=code,
            error_message=error_message,
            extra={"raw_data": data},
        )

    def verify_payment(
        self,
        *,
        authority: str,
        amount: int,
    ) -> PaymentVerifyResult:
        """
        تأیید نهایی پرداخت با زرین‌پال.

        کد 100 success و کد 101 already verified تلقی می‌شود. مقدار
        `verified_amount` برابر amount ورودی است چون زرین‌پال amount را در
        request verify اعتبارسنجی می‌کند.
        """
        payload = {
            "merchant_id": self.merchant_id,
            "authority": authority,
            "amount": amount,
        }
        response_payload, transport_error = self._post_json(
            url=self.verify_url,
            payload=payload,
            timeout=self.VERIFY_TIMEOUT_SECONDS,
            operation="verify_payment",
        )
        if transport_error:
            return PaymentVerifyResult(
                success=False,
                gateway_status="transport_error",
                error_message=transport_error,
            )

        data = self._extract_data(response_payload)
        code = self._extract_code(data)

        if code in {self.SUCCESS_CODE, self.ALREADY_VERIFIED_CODE}:
            ref_id = str(data.get("ref_id") or "")
            logger.info(
                "Zarinpal verify_payment succeeded authority=%s ref_id=%s status=%s",
                authority,
                ref_id,
                code,
            )
            return PaymentVerifyResult(
                success=True,
                already_verified=code == self.ALREADY_VERIFIED_CODE,
                ref_id=ref_id,
                verified_amount=amount,
                gateway_status=code,
                extra={"raw_data": data},
            )

        error_message = self._extract_error_message(response_payload)
        logger.warning(
            "Zarinpal verify_payment failed authority=%s status=%s error=%s",
            authority,
            code,
            error_message,
        )
        return PaymentVerifyResult(
            success=False,
            gateway_status=code,
            error_message=error_message,
            extra={"raw_data": data},
        )

    @staticmethod
    def _build_request_metadata(
        *,
        mobile: str,
        email: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """ساخت metadata ارسالی به زرین‌پال بدون مقادیر خالی."""
        result: dict[str, Any] = {}
        if mobile:
            result["mobile"] = mobile
        if email:
            result["email"] = email
        if metadata:
            result.update(metadata)
        return result

    @staticmethod
    def _post_json(
        *,
        url: str,
        payload: dict[str, Any],
        timeout: int,
        operation: str,
    ) -> tuple[dict[str, Any], str]:
        """
        POST JSON امن با timeout و error normalization.

        Returns:
            (payload, error_message). اگر error_message خالی باشد، payload معتبر است.
        """
        try:
            response = requests.post(url, json=payload, timeout=timeout)
        except requests.exceptions.Timeout:
            logger.warning("Zarinpal %s timed out url=%s", operation, url)
            return {}, "درگاه پرداخت در زمان مقرر پاسخ نداد."
        except requests.exceptions.RequestException as exc:
            logger.warning("Zarinpal %s network error url=%s error=%s", operation, url, exc)
            return {}, "ارتباط با درگاه پرداخت برقرار نشد."

        if response.status_code != 200:
            logger.warning(
                "Zarinpal %s HTTP error status=%s body=%s",
                operation,
                response.status_code,
                response.text[:300],
            )
            return {}, f"درگاه پرداخت پاسخ نامعتبر HTTP {response.status_code} برگرداند."

        try:
            data = response.json()
        except ValueError:
            logger.warning("Zarinpal %s returned invalid JSON body=%s", operation, response.text[:300])
            return {}, "درگاه پرداخت پاسخ JSON نامعتبر برگرداند."

        if not isinstance(data, dict):
            logger.warning("Zarinpal %s returned non-object JSON type=%s", operation, type(data).__name__)
            return {}, "درگاه پرداخت پاسخ غیرمنتظره برگرداند."

        return data, ""

    @staticmethod
    def _extract_data(payload: dict[str, Any]) -> dict[str, Any]:
        """استخراج بخش data از response زرین‌پال."""
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    @classmethod
    def _extract_code(cls, data: dict[str, Any]) -> str:
        """استخراج code/status از بخش data و تبدیل آن به string پایدار."""
        code = data.get("code", "")
        return str(code) if code is not None else ""

    @staticmethod
    def _extract_error_message(payload: dict[str, Any]) -> str:
        """استخراج پیام خطای خوانا از قالب‌های مختلف errors زرین‌پال."""
        errors = payload.get("errors")

        if isinstance(errors, dict):
            message = errors.get("message") or errors.get("code")
            if message:
                return str(message)

            validations = errors.get("validations")
            if isinstance(validations, list) and validations:
                return str(validations[0])

        if isinstance(errors, list) and errors:
            first_error = errors[0]
            if isinstance(first_error, dict):
                return str(first_error.get("message") or first_error.get("code") or first_error)
            return str(first_error)

        data = payload.get("data")
        if isinstance(data, dict) and data.get("message"):
            return str(data["message"])

        return "درگاه پرداخت درخواست را رد کرد."
