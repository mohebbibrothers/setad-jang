"""
Tests — apps.authentication.backends

این تست‌ها contract مربوط به MultiIdentifierBackend را پوشش می‌دهند:

- احراز هویت با email
- احراز هویت با phone_number
- سازگاری با kwargs مثل email=
- رد کردن password اشتباه
- رد کردن کاربر inactive
- رفتار درست در نبود identifier
- اجرای dummy hash path در حالت user-not-found برای timing mitigation
"""

from __future__ import annotations

import pytest
from django.contrib.auth import authenticate, get_user_model

from apps.authentication import backends
from apps.authentication.models import PrimaryIdentifierKind


def _create_user(
    *,
    email: str = "user@example.com",
    phone_number: str = "+989120000000",
    password: str = "StrongPass!234",
    is_active: bool = True,
):
    User = get_user_model()
    user = User.all_objects.create(
        email=email,
        phone_number=phone_number,
        primary_identifier=PrimaryIdentifierKind.EMAIL,
        is_active=is_active,
    )
    user.set_password(password)
    user.save()
    return user


class TestMultiIdentifierBackend:
    """تست‌های مربوط به backend سفارشی چندشناسه‌ای."""

    def test_authenticates_with_email_username(self, db) -> None:
        user = _create_user()

        authenticated_user = authenticate(
            username="user@example.com",
            password="StrongPass!234",
        )

        assert authenticated_user is not None
        assert authenticated_user.pk == user.pk

    def test_authenticates_with_phone_username(self, db) -> None:
        user = _create_user()

        authenticated_user = authenticate(
            username="+989120000000",
            password="StrongPass!234",
        )

        assert authenticated_user is not None
        assert authenticated_user.pk == user.pk

    def test_authenticates_with_email_kwarg(self, db) -> None:
        user = _create_user()

        authenticated_user = authenticate(
            email="user@example.com",
            password="StrongPass!234",
        )

        assert authenticated_user is not None
        assert authenticated_user.pk == user.pk

    def test_returns_none_for_wrong_password(self, db) -> None:
        _create_user()

        authenticated_user = authenticate(
            username="user@example.com",
            password="WrongPass!999",
        )

        assert authenticated_user is None

    def test_returns_none_for_inactive_user(self, db) -> None:
        _create_user(
            email="inactive@example.com",
            phone_number="+989120000001",
            is_active=False,
        )

        authenticated_user = authenticate(
            username="inactive@example.com",
            password="StrongPass!234",
        )

        assert authenticated_user is None

    def test_returns_none_when_identifier_is_missing(self) -> None:
        backend = backends.MultiIdentifierBackend()

        authenticated_user = backend.authenticate(
            request=None,
            username=None,
            password="StrongPass!234",
        )

        assert authenticated_user is None

    def test_executes_dummy_hash_when_user_does_not_exist(
        self,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured_passwords: list[str | None] = []

        def fake_set_password(self, raw_password: str | None) -> None:
            captured_passwords.append(raw_password)

        monkeypatch.setattr(backends.User, "set_password", fake_set_password)

        backend = backends.MultiIdentifierBackend()
        authenticated_user = backend.authenticate(
            request=None,
            username="missing@example.com",
            password="StrongPass!234",
        )

        assert authenticated_user is None
        assert captured_passwords == ["StrongPass!234"]
