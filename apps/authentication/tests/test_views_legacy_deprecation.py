"""
Tests — apps.authentication.views (legacy deprecation headers)

این تست‌ها بررسی می‌کنند که endpointهای legacy auth v1:
- headerهای deprecation را برگردانند
- successor link درست داشته باشند
- در success path و error path هر دو این contract را حفظ کنند
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.urls import reverse

from apps.authentication.deprecation import (
    DEPRECATION_HEADER,
    SUCCESSOR_LINK_HEADER,
)
from apps.authentication.models import PrimaryIdentifierKind
from apps.authentication.views import (
    LEGACY_LOGIN_SUCCESSOR,
    LEGACY_PASSWORD_FORGOT_SUCCESSOR,
    LEGACY_REGISTER_SUCCESSOR,
    LEGACY_VERIFY_EMAIL_SUCCESSOR,
)
from tests.factories.auth import UserFactory

pytestmark = pytest.mark.django_db


def _auth_url(name: str) -> str:
    return reverse(f"authentication:{name}")


def _assert_deprecated(response, *, successor: str) -> None:
    assert response[DEPRECATION_HEADER] == "true"
    assert response[SUCCESSOR_LINK_HEADER] == (f'<{successor}>; rel="successor-version"')


class TestLegacyAuthDeprecationHeaders:
    """Deprecation contract tests for legacy auth-v1 endpoints."""

    def test_register_success_includes_deprecation_headers(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "apps.authentication.views_legacy.register_user",
            lambda **kwargs: SimpleNamespace(email="legacy-register@test.local"),
        )

        response = api_client.post(
            _auth_url("register"),
            data={
                "email": "legacy-register@test.local",
                "password": "StrongPass!234",
                "first_name": "amir",
                "last_name": "legacy",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["success"] is True
        _assert_deprecated(response, successor=LEGACY_REGISTER_SUCCESSOR)

    def test_login_error_includes_deprecation_headers(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "apps.authentication.views_legacy.login_user",
            lambda **kwargs: None,
        )

        response = api_client.post(
            _auth_url("login"),
            data={
                "email": "legacy-login@test.local",
                "password": "WrongPass!999",
            },
            format="json",
        )

        assert response.status_code == 401
        assert response.data["success"] is False
        _assert_deprecated(response, successor=LEGACY_LOGIN_SUCCESSOR)

    def test_forgot_password_success_includes_deprecation_headers(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "apps.authentication.views_password.get_active_user_by_email",
            lambda email: None,
        )

        response = api_client.post(
            _auth_url("password-forgot"),
            data={"email": "legacy-forgot@test.local"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        _assert_deprecated(response, successor=LEGACY_PASSWORD_FORGOT_SUCCESSOR)

    def test_verify_email_not_found_includes_deprecation_headers(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "apps.authentication.views_legacy.get_user_by_email",
            lambda email: None,
        )

        response = api_client.post(
            _auth_url("verify-email"),
            data={
                "email": "missing@test.local",
                "code": "123456",
            },
            format="json",
        )

        assert response.status_code == 404
        assert response.data["success"] is False
        _assert_deprecated(response, successor=LEGACY_VERIFY_EMAIL_SUCCESSOR)

    def test_login_success_includes_deprecation_headers(
        self,
        api_client,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = UserFactory(
            email="legacy-success@test.local",
            primary_identifier=PrimaryIdentifierKind.EMAIL,
            is_email_verified=True,
        )

        monkeypatch.setattr(
            "apps.authentication.views_legacy.login_user",
            lambda **kwargs: {
                "user": user,
                "tokens": {
                    "access": "access-token",
                    "refresh": "refresh-token",
                },
            },
        )

        response = api_client.post(
            _auth_url("login"),
            data={
                "email": "legacy-success@test.local",
                "password": "StrongPass!234",
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.data["success"] is True
        _assert_deprecated(response, successor=LEGACY_LOGIN_SUCCESSOR)
