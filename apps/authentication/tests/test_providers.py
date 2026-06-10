"""
Tests — apps.authentication.providers

این تست‌ها contract لایه‌ی provider را پوشش می‌دهند:

- Email provider:
  - ارسال موفق از طریق Django mail backend
  - wrap کردن خطای backend در exception سطح provider

- SMS placeholder provider:
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

        def fake_send_mail(
            *,
            subject: str,
            message: str,
            from_email: str,
            recipient_list: list[str],
            fail_silently: bool,
        ) -> int:
            sent_payload["subject"] = subject
            sent_payload["message"] = message
            sent_payload["from_email"] = from_email
            sent_payload["recipient_list"] = recipient_list
            sent_payload["fail_silently"] = fail_silently
            return 1

        settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
        monkeypatch.setattr(providers, "send_mail", fake_send_mail)

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
        assert sent_payload["fail_silently"] is False

    def test_wraps_backend_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fake_send_mail(**kwargs: object) -> int:
            raise RuntimeError("smtp unavailable")

        monkeypatch.setattr(providers, "send_mail", fake_send_mail)

        provider = providers.EmailOTPProvider()

        with pytest.raises(providers.OTPDeliveryFailedError, match="email delivery"):
            provider.send(
                recipient="user@example.com",
                code="12345",
                purpose="password_reset",
            )


# ============================================================
# SMS placeholder provider
# ============================================================


class TestConsoleSMSOTPProvider:
    """تست‌های مربوط به SMS placeholder provider."""

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
