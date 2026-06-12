"""Production Phase 4 provider readiness and adapter tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from django.test import override_settings

from apps.authentication import providers
from apps.core.provider_readiness import (
    check_email_provider_readiness,
    check_payment_provider_readiness,
    check_sms_provider_readiness,
    get_provider_readiness_summary,
)


class TestHTTPOTPProvider:
    """Generic HTTP SMS provider contract tests."""

    @override_settings(SMS_API_URL="https://sms.example.test/send", SMS_API_KEY="test-key", SMS_SENDER="SETAD")
    def test_http_sms_provider_posts_generic_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}

        def fake_post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            captured["timeout"] = timeout
            response = MagicMock()
            response.status_code = 200
            response.text = "ok"
            return response

        monkeypatch.setattr(providers.requests, "post", fake_post)

        provider = providers.HTTPAPIOTPProvider()
        assert provider.send(recipient="+989120000000", code="12345", purpose="login") is True
        assert captured["url"] == "https://sms.example.test/send"
        assert captured["json"]["to"] == "+989120000000"
        assert "12345" in captured["json"]["message"]
        assert captured["json"]["sender"] == "SETAD"
        assert captured["headers"]["Authorization"] == "Bearer test-key"

    @override_settings(SMS_API_URL="", SMS_API_KEY="")
    def test_http_sms_provider_fails_loud_when_not_configured(self) -> None:
        provider = providers.HTTPAPIOTPProvider()

        with pytest.raises(providers.OTPDeliveryFailedError):
            provider.send(recipient="+989120000000", code="12345", purpose="login")

    @override_settings(OTP_SMS_PROVIDER="http")
    def test_factory_returns_http_sms_provider(self) -> None:
        provider = providers.get_sms_otp_provider()

        assert isinstance(provider, providers.HTTPAPIOTPProvider)


class TestProviderReadiness:
    """Provider readiness diagnostics tests."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp-relay.brevo.com",
        EMAIL_PORT=587,
        EMAIL_HOST_USER="brevo-user",
        EMAIL_HOST_PASSWORD="brevo-key",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_email_readiness_accepts_brevo_style_smtp_config(self) -> None:
        result = check_email_provider_readiness()

        assert result.ready is True
        assert result.mode == "smtp"

    @override_settings(DEBUG=False, OTP_SMS_PROVIDER="console")
    def test_sms_console_is_not_production_ready(self) -> None:
        result = check_sms_provider_readiness()

        assert result.ready is False
        assert result.mode == "console"

    @override_settings(OTP_SMS_PROVIDER="http", SMS_API_URL="https://sms.example.test/send", SMS_API_KEY="key")
    def test_http_sms_readiness_requires_url_and_key(self) -> None:
        result = check_sms_provider_readiness()

        assert result.ready is True
        assert result.mode == "http"

    @override_settings(MADADKAR_PAYMENT_PROVIDER="zarinpal", MADADKAR_ZARINPAL_MERCHANT_ID="merchant")
    def test_zarinpal_readiness_requires_merchant_id(self) -> None:
        result = check_payment_provider_readiness()

        assert result.ready is True
        assert result.mode == "zarinpal"

    @override_settings(DEBUG=False, MADADKAR_PAYMENT_PROVIDER="sandbox")
    def test_sandbox_payment_is_not_production_ready(self) -> None:
        result = check_payment_provider_readiness()

        assert result.ready is False
        assert result.mode == "sandbox"

    def test_provider_summary_contains_email_sms_payment(self) -> None:
        summary = get_provider_readiness_summary()

        assert set(summary.keys()) == {"email", "sms", "payment"}
