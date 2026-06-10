"""
Tests — apps.authentication.views (identifier management endpoints)

پوشش این فایل:
- identifier add request (phone → attach به email user)
- identifier add verify (تأیید و attach نهایی)
- make primary (تغییر شناسه اصلی)
- reject اگر identifier قبلاً verified باشد
- reject اگر channel قبلاً occupied باشد
- reject اگر identifier برای user دیگری باشد
- reject اگر make-primary روی unverified باشد
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.authentication import (
    otp as otp_module,
    providers as provider_module,
    serializers as auth_serializers,
)
from apps.authentication.models import OTPCode, PrimaryIdentifierKind, User
from tests.factories.auth import UserFactory

pytestmark = pytest.mark.django_db

FIXED_OTP_CODE = "12345"


def _auth_url(name: str) -> str:
    return reverse(f"authentication:{name}")


def _patch_fixed_otp_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(otp_module, "_generate_code", lambda: FIXED_OTP_CODE)


def _patch_sms_delivery_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_module.ConsoleSMSOTPProvider,
        "send",
        lambda self, recipient, code, purpose: True,
    )


def _patch_email_delivery_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_module, "send_mail", lambda **kwargs: 1)


def _patch_email_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    bypass کردن validation ایمیل برای email‌های test.local.
    """
    monkeypatch.setattr(
        auth_serializers,
        "validate_email_for_signup",
        lambda email, **kwargs: None,
    )
    monkeypatch.setattr(provider_module, "send_mail", lambda **kwargs: 1)


def _create_email_user(
    *,
    email: str = "user@test.local",
    password: str = "StrongPass!234",
    is_email_verified: bool = True,
) -> User:
    return UserFactory(
        email=email,
        primary_identifier=PrimaryIdentifierKind.EMAIL,
        is_email_verified=is_email_verified,
        password=password,
    )


def _create_phone_user(
    *,
    phone_number: str = "+989120000000",
    password: str = "StrongPass!234",
    is_phone_verified: bool = True,
) -> User:
    """
    ساخت کاربر واقعاً phone-first و بدون email.

    مهم:
    از UserFactory استفاده نمی‌کنیم چون آن به‌صورت پیش‌فرض email می‌سازد
    و باعث می‌شود channel ایمیل از قبل occupied باشد.
    """
    UserModel = get_user_model()
    return UserModel.objects.create_user(
        email=None,
        phone_number=phone_number,
        password=password,
        primary_identifier=PrimaryIdentifierKind.PHONE,
        is_phone_verified=is_phone_verified,
    )


class TestIdentifierAddRequest:
    """تست‌های مربوط به endpoint درخواست اتصال شناسه ثانویه."""

    def test_email_user_can_request_phone_attachment(
        self,
        authenticated_client,
        regular_user,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_sms_delivery_success(monkeypatch)

        response = authenticated_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": "09120000000"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["message"] == "کد تأیید ارسال شد."

        otp = OTPCode.objects.get(identifier_value="+989120000000")
        assert otp.identifier_kind == PrimaryIdentifierKind.PHONE
        assert otp.is_used is False

    def test_phone_user_can_request_email_attachment(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = _create_phone_user()
        api_client.force_authenticate(user=user)
        _patch_email_validation(monkeypatch)
        _patch_email_delivery_success(monkeypatch)

        response = api_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": "new@test.local"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

    def test_rejects_if_email_already_verified_for_user(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = _create_email_user(is_email_verified=True)
        api_client.force_authenticate(user=user)
        _patch_email_validation(monkeypatch)

        response = api_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": user.email},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False

        errors_text = str(response.data)
        assert "تأیید شده" in errors_text

    def test_rejects_if_channel_already_occupied_by_different_value(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = _create_email_user()
        user.phone_number = "+989120000001"
        user.is_phone_verified = True
        user.save()
        api_client.force_authenticate(user=user)
        _patch_sms_delivery_success(monkeypatch)

        response = api_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": "09120000002"},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False

    def test_rejects_if_identifier_belongs_to_another_user(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _create_phone_user(phone_number="+989120000099")
        user = _create_email_user(email="user2@test.local")
        api_client.force_authenticate(user=user)
        _patch_sms_delivery_success(monkeypatch)

        response = api_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": "+989120000099"},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False

    def test_requires_authentication(self, api_client) -> None:
        response = api_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": "09120000000"},
            format="json",
        )

        assert response.status_code == 401


class TestIdentifierAddVerify:
    """تست‌های مربوط به endpoint تأیید و اتصال نهایی شناسه ثانویه."""

    def test_email_user_can_attach_and_verify_phone(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = _create_email_user()
        api_client.force_authenticate(user=user)
        _patch_fixed_otp_code(monkeypatch)
        _patch_sms_delivery_success(monkeypatch)

        request_response = api_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": "09120000000"},
            format="json",
        )
        assert request_response.status_code == 200

        verify_response = api_client.post(
            _auth_url("identifier-add-verify"),
            data={
                "identifier": "09120000000",
                "code": FIXED_OTP_CODE,
            },
            format="json",
        )

        assert verify_response.status_code == 200
        assert verify_response.data["success"] is True

        user.refresh_from_db()
        assert user.phone_number == "+989120000000"
        assert user.is_phone_verified is True

        otp = OTPCode.objects.get(identifier_value="+989120000000")
        assert otp.is_used is True

    def test_phone_user_can_attach_and_verify_email(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = _create_phone_user()
        api_client.force_authenticate(user=user)
        _patch_fixed_otp_code(monkeypatch)
        _patch_email_validation(monkeypatch)
        _patch_email_delivery_success(monkeypatch)

        request_response = api_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": "newmail@test.local"},
            format="json",
        )
        assert request_response.status_code == 200

        verify_response = api_client.post(
            _auth_url("identifier-add-verify"),
            data={
                "identifier": "newmail@test.local",
                "code": FIXED_OTP_CODE,
            },
            format="json",
        )

        assert verify_response.status_code == 200

        user.refresh_from_db()
        assert user.email == "newmail@test.local"
        assert user.is_email_verified is True

    def test_returns_updated_user_data_after_verify(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = _create_email_user()
        api_client.force_authenticate(user=user)
        _patch_fixed_otp_code(monkeypatch)
        _patch_sms_delivery_success(monkeypatch)

        api_client.post(
            _auth_url("identifier-add-request"),
            data={"identifier": "09120000000"},
            format="json",
        )

        verify_response = api_client.post(
            _auth_url("identifier-add-verify"),
            data={
                "identifier": "09120000000",
                "code": FIXED_OTP_CODE,
            },
            format="json",
        )

        assert verify_response.status_code == 200
        assert verify_response.data["data"]["id"] == user.id

    def test_requires_authentication(self, api_client) -> None:
        response = api_client.post(
            _auth_url("identifier-add-verify"),
            data={"identifier": "09120000000", "code": "12345"},
            format="json",
        )

        assert response.status_code == 401


class TestIdentifierMakePrimary:
    """تست‌های مربوط به endpoint تغییر شناسه اصلی."""

    def test_email_user_can_switch_primary_to_phone(
        self,
        api_client,
    ) -> None:
        user = _create_email_user()
        user.phone_number = "+989120000000"
        user.is_phone_verified = True
        user.save()
        api_client.force_authenticate(user=user)

        response = api_client.post(
            _auth_url("identifier-make-primary"),
            data={"identifier_kind": "phone"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

        user.refresh_from_db()
        assert user.primary_identifier == PrimaryIdentifierKind.PHONE

    def test_phone_user_can_switch_primary_to_email(
        self,
        api_client,
    ) -> None:
        user = _create_phone_user()
        user.email = "also@test.local"
        user.is_email_verified = True
        user.save()
        api_client.force_authenticate(user=user)

        response = api_client.post(
            _auth_url("identifier-make-primary"),
            data={"identifier_kind": "email"},
            format="json",
        )

        assert response.status_code == 200

        user.refresh_from_db()
        assert user.primary_identifier == PrimaryIdentifierKind.EMAIL

    def test_rejects_if_phone_not_attached(
        self,
        api_client,
    ) -> None:
        user = _create_email_user()
        api_client.force_authenticate(user=user)

        response = api_client.post(
            _auth_url("identifier-make-primary"),
            data={"identifier_kind": "phone"},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False

        errors_text = str(response.data)
        assert "ثبت نشده" in errors_text

    def test_rejects_if_phone_attached_but_not_verified(
        self,
        api_client,
    ) -> None:
        user = _create_email_user()
        user.phone_number = "+989120000000"
        user.is_phone_verified = False
        user.save()
        api_client.force_authenticate(user=user)

        response = api_client.post(
            _auth_url("identifier-make-primary"),
            data={"identifier_kind": "phone"},
            format="json",
        )

        assert response.status_code == 400
        assert response.data["success"] is False

        errors_text = str(response.data)
        assert "تأیید نشده" in errors_text

    def test_is_idempotent_when_already_primary(
        self,
        api_client,
    ) -> None:
        user = _create_email_user()
        api_client.force_authenticate(user=user)

        response = api_client.post(
            _auth_url("identifier-make-primary"),
            data={"identifier_kind": "email"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True

        user.refresh_from_db()
        assert user.primary_identifier == PrimaryIdentifierKind.EMAIL

    def test_requires_authentication(self, api_client) -> None:
        response = api_client.post(
            _auth_url("identifier-make-primary"),
            data={"identifier_kind": "phone"},
            format="json",
        )

        assert response.status_code == 401
