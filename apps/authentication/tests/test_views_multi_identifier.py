"""
Tests — apps.authentication.views (multi-identifier auth endpoints)

پوشش این فایل:
- signup request با phone
- signup request با email
- honeypot integration
- global OTP guard integration
- signup verify -> user creation + JWT
- password login with phone
- OTP login request/verify
- forgot password request/confirm
- enumeration-safe responses
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.authentication import (
    otp as otp_module,
    providers as provider_module,
    serializers as auth_serializers,
    views_common as auth_guard,  # patch-where-used پس از تفکیک P3-16
)
from apps.authentication.choices import OTPPurpose
from apps.authentication.models import OTPCode, PrimaryIdentifierKind, User
from tests.factories.auth import UserFactory

pytestmark = pytest.mark.django_db

FIXED_OTP_CODE = "246810"  # ۶ رقم = طول پیش‌فرض موتور (AUTH_OTP_CODE_LENGTH)


def _auth_url(name: str) -> str:
    return reverse(f"authentication:{name}")


def _patch_fixed_otp_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(otp_module, "_generate_code", lambda: FIXED_OTP_CODE)


def _patch_email_signup_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_serializers,
        "validate_email_for_signup",
        lambda email: None,
    )
    monkeypatch.setattr(provider_module, "send_text_email", lambda **kwargs: 1)


def _patch_sms_delivery_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_module.ConsoleSMSOTPProvider,
        "send",
        lambda self, recipient, code, purpose: True,
    )


def _create_verified_phone_user(
    *,
    phone_number: str = "+989120000000",
    password: str = "StrongPass!234",
) -> User:
    return UserFactory(
        phone_number=phone_number,
        primary_identifier=PrimaryIdentifierKind.PHONE,
        is_phone_verified=True,
        password=password,
    )


class TestMultiIdentifierAuthViews:
    """Integration tests for the new public auth v2 endpoints."""

    def test_signup_request_sends_signup_otp_for_phone_identifier(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_sms_delivery_success(monkeypatch)

        response = api_client.post(
            _auth_url("signup-request"),
            data={"identifier": "09120000000"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["message"] == "کد ثبت‌نام با موفقیت ارسال شد."

        otp = OTPCode.objects.get(purpose=OTPPurpose.SIGNUP)
        assert otp.identifier_kind == PrimaryIdentifierKind.PHONE
        assert otp.identifier_value == "+989120000000"
        assert otp.is_used is False

    def test_signup_request_accepts_email_identifier_and_normalizes_it(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_email_signup_validation(monkeypatch)

        response = api_client.post(
            _auth_url("signup-request"),
            data={"identifier": " USER@Test.Local "},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

        otp = OTPCode.objects.get(purpose=OTPPurpose.SIGNUP)
        assert otp.identifier_kind == PrimaryIdentifierKind.EMAIL
        assert otp.identifier_value == "user@test.local"

    def test_signup_request_rejects_honeypot_payload(
        self,
        api_client,
    ) -> None:
        response = api_client.post(
            _auth_url("signup-request"),
            data={
                "identifier": "09120000000",
                "website": "spam-bot",
            },
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False
        assert response.data["message"] == "درخواست نامعتبر است."
        assert OTPCode.objects.count() == 0

    def test_signup_request_returns_429_when_global_guard_is_tripped(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(auth_guard, "is_global_otp_guard_tripped", lambda: True)

        response = api_client.post(
            _auth_url("signup-request"),
            data={"identifier": "09120000000"},
            format="json",
        )

        assert response.status_code == 429
        assert response.data["success"] is False
        assert OTPCode.objects.count() == 0

    def test_signup_verify_creates_phone_user_and_returns_tokens(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_fixed_otp_code(monkeypatch)
        _patch_sms_delivery_success(monkeypatch)

        request_response = api_client.post(
            _auth_url("signup-request"),
            data={"identifier": "09120000000"},
            format="json",
        )
        assert request_response.status_code == 200

        verify_response = api_client.post(
            _auth_url("signup-verify"),
            data={
                "identifier": "09120000000",
                "code": FIXED_OTP_CODE,
                "password": "StrongPass!234",
                "first_name": "amir",
                "last_name": "test",
            },
            format="json",
        )

        assert verify_response.status_code == 200
        assert verify_response.data["success"] is True
        assert "access" in verify_response.data["data"]["tokens"]
        assert "refresh" in verify_response.data["data"]["tokens"]

        user = User.all_objects.get(phone_number="+989120000000")
        assert user.primary_identifier == PrimaryIdentifierKind.PHONE
        assert user.is_phone_verified is True
        assert user.check_password("StrongPass!234") is True
        assert verify_response.data["data"]["user"]["id"] == user.id

        otp = OTPCode.objects.get(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value="+989120000000",
            purpose=OTPPurpose.SIGNUP,
        )
        assert otp.is_used is True

    def test_login_password_authenticates_with_phone_identifier(
        self,
        api_client,
    ) -> None:
        user = _create_verified_phone_user()

        response = api_client.post(
            _auth_url("login-password"),
            data={
                "identifier": "+989120000000",
                "password": "StrongPass!234",
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["data"]["user"]["id"] == user.id
        assert "access" in response.data["data"]["tokens"]

    def test_login_password_returns_401_for_wrong_password(
        self,
        api_client,
    ) -> None:
        _create_verified_phone_user()

        response = api_client.post(
            _auth_url("login-password"),
            data={
                "identifier": "+989120000000",
                "password": "WrongPass!999",
            },
            format="json",
        )

        assert response.status_code == 401
        assert response.data["success"] is False
        assert response.data["message"] == "شناسه یا رمز عبور اشتباه است."

    def test_login_otp_request_is_enumeration_safe_for_missing_identifier(
        self,
        api_client,
    ) -> None:
        response = api_client.post(
            _auth_url("login-otp-request"),
            data={"identifier": "+989120009999"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert (
            response.data["message"] == "اگر حسابی با این شناسه وجود داشته باشد، کد ورود ارسال شد."
        )
        assert OTPCode.objects.count() == 0

    def test_login_otp_request_is_enumeration_safe_for_inactive_identifier(
        self,
        api_client,
    ) -> None:
        _create_verified_phone_user(phone_number="+989120000123")
        User.all_objects.filter(phone_number="+989120000123").update(is_active=False)

        response = api_client.post(
            _auth_url("login-otp-request"),
            data={"identifier": "+989120000123"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert (
            response.data["message"] == "اگر حسابی با این شناسه وجود داشته باشد، کد ورود ارسال شد."
        )
        assert OTPCode.objects.count() == 0

    def test_login_otp_verify_returns_tokens_for_phone_user(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _create_verified_phone_user()
        _patch_fixed_otp_code(monkeypatch)
        _patch_sms_delivery_success(monkeypatch)

        request_response = api_client.post(
            _auth_url("login-otp-request"),
            data={"identifier": "+989120000000"},
            format="json",
        )
        assert request_response.status_code == 200

        verify_response = api_client.post(
            _auth_url("login-otp-verify"),
            data={
                "identifier": "+989120000000",
                "code": FIXED_OTP_CODE,
            },
            format="json",
        )

        assert verify_response.status_code == 200
        assert verify_response.data["success"] is True
        assert "access" in verify_response.data["data"]["tokens"]
        assert "refresh" in verify_response.data["data"]["tokens"]

        otp = OTPCode.objects.get(
            identifier_kind=PrimaryIdentifierKind.PHONE,
            identifier_value="+989120000000",
            purpose=OTPPurpose.LOGIN,
        )
        assert otp.is_used is True

    def test_password_forgot_request_is_enumeration_safe_for_missing_identifier(
        self,
        api_client,
    ) -> None:
        response = api_client.post(
            _auth_url("password-forgot-request-identifier"),
            data={"identifier": "+989120009999"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert (
            response.data["message"]
            == "اگر حسابی با این شناسه وجود داشته باشد، کد بازیابی ارسال شد."
        )
        assert OTPCode.objects.count() == 0

    def test_password_forgot_request_is_enumeration_safe_for_inactive_identifier(
        self,
        api_client,
    ) -> None:
        _create_verified_phone_user(phone_number="+989120000124")
        User.all_objects.filter(phone_number="+989120000124").update(is_active=False)

        response = api_client.post(
            _auth_url("password-forgot-request-identifier"),
            data={"identifier": "+989120000124"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert (
            response.data["message"]
            == "اگر حسابی با این شناسه وجود داشته باشد، کد بازیابی ارسال شد."
        )
        assert OTPCode.objects.count() == 0

    def test_password_forgot_confirm_changes_password_for_phone_identifier(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = _create_verified_phone_user()
        _patch_fixed_otp_code(monkeypatch)
        _patch_sms_delivery_success(monkeypatch)

        request_response = api_client.post(
            _auth_url("password-forgot-request-identifier"),
            data={"identifier": "+989120000000"},
            format="json",
        )
        assert request_response.status_code == 200

        confirm_response = api_client.post(
            _auth_url("password-forgot-confirm-identifier"),
            data={
                "identifier": "+989120000000",
                "code": FIXED_OTP_CODE,
                "new_password": "NewStrongPass!456",
            },
            format="json",
        )

        assert confirm_response.status_code == 200
        assert confirm_response.data["success"] is True
        assert confirm_response.data["message"] == "رمز عبور با موفقیت تغییر کرد."

        user.refresh_from_db()
        assert user.check_password("NewStrongPass!456") is True

        login_response = api_client.post(
            _auth_url("login-password"),
            data={
                "identifier": "+989120000000",
                "password": "NewStrongPass!456",
            },
            format="json",
        )
        assert login_response.status_code == 200
