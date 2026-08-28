"""Provider readiness checks for production configuration."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class ProviderReadinessResult:
    """Readiness result for an external provider configuration."""

    name: str
    ready: bool
    mode: str
    detail: str = ""


def _default_mailer_config() -> dict[str, object]:
    """Return ``MAILERS["default"]`` — از Django 6.1 جایگزین EMAIL_* شده است."""
    mailers = getattr(settings, "MAILERS", {})
    return mailers.get("default", {})


def check_email_provider_readiness() -> ProviderReadinessResult:
    """Check SMTP/email provider configuration without sending an email."""
    mailer = _default_mailer_config()
    backend = str(mailer.get("BACKEND", ""))
    options = mailer.get("OPTIONS", {})
    if not isinstance(options, dict):
        options = {}
    if backend.endswith("ReadableConsoleEmailBackend"):
        return ProviderReadinessResult(
            "email", settings.DEBUG, "console", "Console email backend is development-only."
        )
    required = [options.get("host"), options.get("port"), settings.DEFAULT_FROM_EMAIL]
    credentials_present = bool(options.get("username") and options.get("password"))
    ready = all(required) and credentials_present
    return ProviderReadinessResult(
        "email",
        ready,
        "smtp",
        "SMTP configured." if ready else "SMTP host/from/credentials are incomplete.",
    )


def check_sms_provider_readiness() -> ProviderReadinessResult:
    """Check SMS provider configuration without sending an SMS."""
    provider = getattr(settings, "OTP_SMS_PROVIDER", "console")
    if provider == "console":
        return ProviderReadinessResult(
            "sms", settings.DEBUG, "console", "Console SMS backend is development-only."
        )
    if provider == "http":
        ready = bool(getattr(settings, "SMS_API_URL", "") and getattr(settings, "SMS_API_KEY", ""))
        return ProviderReadinessResult(
            "sms",
            ready,
            "http",
            "HTTP SMS provider configured." if ready else "SMS_API_URL/SMS_API_KEY are required.",
        )
    return ProviderReadinessResult("sms", False, provider, "Unsupported SMS provider.")


def check_payment_provider_readiness() -> ProviderReadinessResult:
    """Check Madadkar payment provider configuration without requesting payment."""
    provider = getattr(settings, "MADADKAR_PAYMENT_PROVIDER", "sandbox")
    if provider == "sandbox":
        return ProviderReadinessResult(
            "payment",
            settings.DEBUG,
            "sandbox",
            "Sandbox payment provider is development/staging only.",
        )
    if provider == "zarinpal":
        ready = bool(getattr(settings, "MADADKAR_ZARINPAL_MERCHANT_ID", ""))
        return ProviderReadinessResult(
            "payment",
            ready,
            "zarinpal",
            "Zarinpal merchant id configured."
            if ready
            else "MADADKAR_ZARINPAL_MERCHANT_ID is required.",
        )
    return ProviderReadinessResult("payment", False, provider, "Unsupported payment provider.")


def get_provider_readiness_summary() -> dict[str, dict[str, object]]:
    """Return provider readiness summary for operational checks/docs/tests."""
    results = [
        check_email_provider_readiness(),
        check_sms_provider_readiness(),
        check_payment_provider_readiness(),
    ]
    return {
        result.name: {
            "ready": result.ready,
            "mode": result.mode,
            "detail": result.detail,
        }
        for result in results
    }
