"""
Authentication service boundary normalization tests.

Serializerها معمولاً identifierها را normalize می‌کنند، اما service layer نباید به
این فرض وابسته باشد. این تست‌ها تضمین می‌کنند public service functions حتی در
فراخوانی مستقیم نیز email/phone خام را به فرم canonical تبدیل می‌کنند.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from apps.authentication import otp as otp_module, services
from apps.authentication.choices import OTPPurpose
from apps.authentication.models import OTPCode, PrimaryIdentifierKind, User
from apps.authentication.providers import ConsoleSMSOTPProvider
from tests.factories.auth import UserFactory

pytestmark = pytest.mark.django_db

FIXED_OTP_CODE = "246810"  # ۶ رقم = طول پیش‌فرض موتور (AUTH_OTP_CODE_LENGTH)


def _patch_otp_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch کردن تولید و delivery کد برای تست‌های deterministic service layer."""
    monkeypatch.setattr(otp_module, "_generate_code", lambda: FIXED_OTP_CODE)
    monkeypatch.setattr(
        ConsoleSMSOTPProvider,
        "send",
        lambda self, recipient, code, purpose: True,
    )


def _request():
    """ساخت request سبک برای serviceهایی که JWT/login result می‌سازند."""
    return RequestFactory().post("/api/v1/auth/test/")


class TestIdentifierServiceNormalization:
    """تست‌های نرمال‌سازی در boundary سرویس‌های multi-identifier."""

    def test_signup_request_normalizes_raw_email_before_creating_otp(self, monkeypatch):
        _patch_otp_delivery(monkeypatch)

        services.signup_request(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=" USER@Test.Local ",
        )

        otp = OTPCode.objects.get(purpose=OTPPurpose.SIGNUP)
        assert otp.identifier_value == "user@test.local"

    def test_signup_verify_normalizes_raw_phone_before_creating_user(self, monkeypatch):
        _patch_otp_delivery(monkeypatch)
        services.signup_request(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value="09120000000",
        )

        result = services.signup_verify(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value="0912 000 0000",
            code=FIXED_OTP_CODE,
            password="StrongPass!234",
            request=_request(),
        )

        user = User.all_objects.get(phone_number="+989120000000")
        assert user.is_phone_verified is True
        assert result["user"] == user

    def test_login_with_password_normalizes_raw_email(self):
        user = UserFactory(
            email="user@test.local",
            is_email_verified=True,
            primary_identifier=PrimaryIdentifierKind.EMAIL,
            password="StrongPass!234",
        )

        result = services.login_with_password(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=" USER@Test.Local ",
            password="StrongPass!234",
            request=_request(),
        )

        assert result["user"] == user
        assert "access" in result["tokens"]

    def test_forgot_password_request_normalizes_raw_phone_before_creating_otp(self, monkeypatch):
        _patch_otp_delivery(monkeypatch)
        UserFactory(
            phone_number="+989120000000",
            primary_identifier=PrimaryIdentifierKind.PHONE,
            is_phone_verified=True,
        )

        services.forgot_password_request(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value="0912 000 0000",
        )

        otp = OTPCode.objects.get(purpose=OTPPurpose.PASSWORD_RESET)
        assert otp.identifier_kind == PrimaryIdentifierKind.PHONE
        assert otp.identifier_value == "+989120000000"

    def test_login_otp_verify_normalizes_raw_phone_before_lookup(self, monkeypatch):
        _patch_otp_delivery(monkeypatch)
        user = UserFactory(
            phone_number="+989120000000",
            primary_identifier=PrimaryIdentifierKind.PHONE,
            is_phone_verified=True,
        )
        services.login_otp_request(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value="09120000000",
        )

        result = services.login_otp_verify(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value="0912 000 0000",
            code=FIXED_OTP_CODE,
            request=_request(),
        )

        assert result["user"] == user
        assert "refresh" in result["tokens"]
