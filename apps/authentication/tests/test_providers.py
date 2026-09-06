"""
Tests — apps.authentication.providers

این تست‌ها contract لایه‌ی provider را پوشش می‌دهند:

- Email provider:
  - ارسال موفق از طریق Django mail backend
  - wrap کردن خطای backend در exception سطح provider

- SMS console development provider:
  - در DEBUG باید success برگرداند
  - در production باید fail loud کند

- Factory:
  - explicit channel selection
  - legacy compatibility با OTP_PROVIDER=sms
  - reject کردن backend نامعتبر

- OTP integration:
  - اگر provider در زمان delivery fail شود، transaction باید rollback شود
  - OTP قبلی نباید invalidate شود
  - OTP جدید نباید در DB باقی بماند
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.authentication import otp as otp_service, providers
from apps.authentication.choices import OTPPurpose
from apps.authentication.models import OTPCode, PrimaryIdentifierKind


class _FailingProvider:
    """Provider ساختگی که همیشه در delivery fail می‌شود."""

    def send(self, recipient: str, code: str, purpose: str) -> bool:
        raise providers.OTPDeliveryProviderError("simulated provider outage")


# ============================================================
# Email provider
# ============================================================


class TestEmailOTPProvider:
    """تست‌های مربوط به Email delivery provider."""

    def test_sends_email_via_django_backend(
        self,
        monkeypatch: pytest.MonkeyPatch,
        settings,
    ) -> None:
        sent_payload: dict[str, object] = {}

        def fake_send_text_email(
            *,
            subject: str,
            message: str,
            from_email: str,
            recipient_list: list[str],
        ) -> int:
            sent_payload["subject"] = subject
            sent_payload["message"] = message
            sent_payload["from_email"] = from_email
            sent_payload["recipient_list"] = recipient_list
            return 1

        settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
        monkeypatch.setattr(providers, "send_text_email", fake_send_text_email)

        provider = providers.EmailOTPProvider()
        result = provider.send(
            recipient="user@example.com",
            code="12345",
            purpose="password_reset",
        )

        assert result is True
        assert sent_payload["subject"] == "بازیابی رمز عبور - ستاد جنگ"
        assert "12345" in str(sent_payload["message"])
        assert sent_payload["from_email"] == "noreply@test.local"
        assert sent_payload["recipient_list"] == ["user@example.com"]

    def test_wraps_backend_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fake_send_text_email(**kwargs: object) -> int:
            raise RuntimeError("smtp unavailable")

        monkeypatch.setattr(providers, "send_text_email", fake_send_text_email)

        provider = providers.EmailOTPProvider()

        with pytest.raises(providers.OTPDeliveryFailedError, match="email delivery"):
            provider.send(
                recipient="user@example.com",
                code="12345",
                purpose="password_reset",
            )


# ============================================================
# SMS console development provider
# ============================================================


class TestConsoleSMSOTPProvider:
    """تست‌های مربوط به SMS console development provider."""

    def test_returns_true_in_debug_mode(self, settings) -> None:
        settings.DEBUG = True

        provider = providers.ConsoleSMSOTPProvider()

        assert (
            provider.send(
                recipient="+989120000000",
                code="12345",
                purpose="login",
            )
            is True
        )

    def test_fails_loud_in_production(self, settings) -> None:
        settings.DEBUG = False

        provider = providers.ConsoleSMSOTPProvider()

        with pytest.raises(
            providers.OTPDeliveryFailedError,
            match="not configured for production",
        ):
            provider.send(
                recipient="+989120000000",
                code="12345",
                purpose="login",
            )


# ============================================================
# Factory
# ============================================================


class TestOTPProviderFactory:
    """تست‌های مربوط به factory و backward compatibility."""

    def test_returns_email_provider_for_explicit_email_channel(self) -> None:
        provider = providers.get_otp_provider(channel="email")

        assert isinstance(provider, providers.EmailOTPProvider)

    def test_accepts_legacy_sms_alias_and_returns_phone_provider(self) -> None:
        provider = providers.get_otp_provider(channel="sms")

        assert isinstance(provider, providers.ConsoleSMSOTPProvider)

    def test_uses_legacy_setting_when_channel_is_omitted(self, settings) -> None:
        settings.OTP_PROVIDER = "sms"

        provider = providers.get_otp_provider()

        assert isinstance(provider, providers.ConsoleSMSOTPProvider)

    def test_rejects_unknown_channel(self) -> None:
        with pytest.raises(providers.UnsupportedOTPChannelError):
            providers.get_otp_provider(channel="pigeon")

    def test_rejects_unknown_sms_backend(self, settings) -> None:
        settings.OTP_SMS_PROVIDER = "kavenegar"

        with pytest.raises(providers.UnsupportedOTPProviderError):
            providers.get_sms_otp_provider()


# ============================================================
# OTP integration rollback
# ============================================================


class TestOTPDeliveryRollback:
    """تست ACID rollback در صورت failure حین delivery."""

    def test_generate_and_send_otp_rolls_back_db_changes_when_provider_fails(
        self,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured_channel: dict[str, str] = {}
        purpose = next(iter(OTPPurpose)).value

        existing_otp = OTPCode.objects.create(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="rollback@example.com",
            purpose=purpose,
            code_hash="x" * 64,
            expires_at=timezone.now() + timedelta(minutes=5),
            attempts=0,
            is_used=False,
        )

        OTPCode.objects.filter(pk=existing_otp.pk).update(
            created_at=timezone.now() - timedelta(seconds=61),
        )
        existing_otp.refresh_from_db()

        def fake_get_otp_provider(channel: str):
            captured_channel["value"] = channel
            return _FailingProvider()

        monkeypatch.setattr(otp_service, "get_otp_provider", fake_get_otp_provider)

        with pytest.raises(otp_service.OTPDeliveryError, match="در ارسال کد"):
            otp_service.generate_and_send_otp(
                identifier_kind=PrimaryIdentifierKind.EMAIL,
                identifier_value="rollback@example.com",
                purpose=purpose,
            )

        existing_otp.refresh_from_db()

        remaining_otps = OTPCode.objects.filter(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value="rollback@example.com",
            purpose=purpose,
        )

        assert captured_channel["value"] == PrimaryIdentifierKind.EMAIL
        assert existing_otp.is_used is False
        assert remaining_otps.count() == 1
        assert remaining_otps.first().pk == existing_otp.pk


# ============================================================
# IranPayamak pattern SMS provider
# ============================================================


class _FakePayamakResponse:
    """Response deterministic برای mock ایران‌پیامک."""

    def __init__(self, *, status_code: int = 201, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {"status": "success", "data": 0}
        self.text = str(self._payload)

    def json(self) -> dict:
        return self._payload


class TestIranPayamakProvider:
    """تست‌های adapter الگوی پیامکی ایران‌پیامک (بدون شبکه واقعی)."""

    @staticmethod
    def _configure(settings) -> None:
        settings.SMS_IRANPAYAMAK_API_KEY = "test-api-key"
        settings.SMS_IRANPAYAMAK_LINE_NUMBER = "50002178584000"
        settings.SMS_IRANPAYAMAK_NUMBER_FORMAT = "persian"
        settings.SMS_IRANPAYAMAK_PATTERN_URL = "https://api.iranpayamak.com/ws/v1/sms/pattern"
        settings.SMS_IRANPAYAMAK_TIMEOUT_SECONDS = 10
        settings.SMS_IRANPAYAMAK_PATTERN_LOGIN = "PATTERN-LOGIN"
        settings.SMS_IRANPAYAMAK_PATTERN_SIGNUP = "PATTERN-SIGNUP"
        settings.SMS_IRANPAYAMAK_PATTERN_PASSWORD_RESET = "PATTERN-RESET"
        settings.SMS_IRANPAYAMAK_PATTERN_IDENTIFIER_ADD = ""

    def test_factory_selects_iranpayamak(self, settings, monkeypatch):
        settings.OTP_SMS_PROVIDER = "iranpayamak"
        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        self._configure(settings)
        provider = providers.get_sms_otp_provider()
        assert isinstance(provider, IranPayamakOTPProvider)

    def test_send_builds_documented_payload_and_headers(self, settings, monkeypatch):
        self._configure(settings)
        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        captured: dict = {}

        def fake_post(url, *, json, headers, timeout):
            captured.update(url=url, json=json, headers=headers, timeout=timeout)
            return _FakePayamakResponse()

        monkeypatch.setattr("apps.authentication.iranpayamak.requests.post", fake_post)

        provider = IranPayamakOTPProvider()
        ok = provider.send(recipient="+989366208105", code="313456", purpose="login")

        assert ok is True
        assert captured["url"] == "https://api.iranpayamak.com/ws/v1/sms/pattern"
        assert captured["headers"]["Api-Key"] == "test-api-key"
        payload = captured["json"]
        assert payload["code"] == "PATTERN-LOGIN"
        assert payload["attributes"] == {"code": "313456"}
        assert payload["recipient"] == "09366208105"
        assert payload["line_number"] == "50002178584000"
        assert payload["number_format"] == "persian"

    @pytest.mark.parametrize(
        ("raw", "normalized"),
        [
            ("+989121234567", "09121234567"),
            ("0098 912 123 4567", "09121234567"),
            ("989121234567", "09121234567"),
            ("0912-123-4567", "09121234567"),
        ],
    )
    def test_recipient_normalization_accepts_common_formats(self, raw, normalized):
        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        assert IranPayamakOTPProvider._normalize_recipient(raw) == normalized

    def test_invalid_recipient_fails_before_network(self, settings, monkeypatch):
        self._configure(settings)
        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        calls: list = []
        monkeypatch.setattr(
            "apps.authentication.iranpayamak.requests.post",
            lambda *a, **k: calls.append(a),
        )

        provider = IranPayamakOTPProvider()
        with pytest.raises(providers.OTPDeliveryFailedError):
            provider.send(recipient="12345", code="1", purpose="login")

        assert calls == []

    def test_missing_api_key_fails_loud(self, settings):
        self._configure(settings)
        settings.SMS_IRANPAYAMAK_API_KEY = ""
        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        with pytest.raises(providers.OTPDeliveryFailedError, match="API key"):
            IranPayamakOTPProvider().send(recipient="09121234567", code="1", purpose="login")

    def test_missing_pattern_for_purpose_fails_loud(self, settings):
        self._configure(settings)
        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        provider = IranPayamakOTPProvider()
        with pytest.raises(providers.OTPDeliveryFailedError, match="identifier_add"):
            provider.send(recipient="09121234567", code="1", purpose="identifier_add")

    def test_vendor_rejection_raises_with_logging(self, settings, monkeypatch):
        self._configure(settings)
        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        def fake_post(url, *, json, headers, timeout):
            return _FakePayamakResponse(
                status_code=400,
                payload={"status": "error", "messages": "کد الگو نامعتبر است."},
            )

        monkeypatch.setattr("apps.authentication.iranpayamak.requests.post", fake_post)

        with pytest.raises(providers.OTPDeliveryFailedError, match="not accepted"):
            IranPayamakOTPProvider().send(recipient="09121234567", code="1", purpose="signup")

    def test_status_ok_but_business_status_error_raises(self, settings, monkeypatch):
        """HTTP 200 + status!=success هم باید fail شود (سند: success در body)."""
        self._configure(settings)
        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        def fake_post(url, *, json, headers, timeout):
            return _FakePayamakResponse(
                status_code=200, payload={"status": "error", "messages": ["line disabled"]}
            )

        monkeypatch.setattr("apps.authentication.iranpayamak.requests.post", fake_post)

        with pytest.raises(providers.OTPDeliveryFailedError, match="not accepted"):
            IranPayamakOTPProvider().send(recipient="09121234567", code="1", purpose="login")

    def test_network_error_is_wrapped(self, settings, monkeypatch):
        self._configure(settings)
        import requests as requests_lib

        from apps.authentication.iranpayamak import IranPayamakOTPProvider

        def fake_post(url, *, json, headers, timeout):
            raise requests_lib.exceptions.ConnectionError("down")

        monkeypatch.setattr("apps.authentication.iranpayamak.requests.post", fake_post)

        with pytest.raises(providers.OTPDeliveryFailedError, match="request failed"):
            IranPayamakOTPProvider().send(recipient="09121234567", code="1", purpose="login")
