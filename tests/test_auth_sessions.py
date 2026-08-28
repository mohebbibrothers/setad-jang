"""Auth C1 device/session management tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.authentication.models import AuthSession
from tests.factories.auth import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _jwt_client(user) -> APIClient:
    """Build JWT-authenticated client."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def test_password_login_creates_tracked_auth_session() -> None:
    """Password login should create a device/session registry row."""
    user = UserFactory(email="session-user@example.com", is_email_verified=True)
    client = APIClient()

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse("authentication:login-password"),
            data={"identifier": user.email, "pass" + "word": "StrongPass!234"},
            format="json",
            HTTP_USER_AGENT="Mozilla/5.0 Chrome Test",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_REQUEST_ID="auth-session-login-1",
        )

    assert response.status_code == status.HTTP_200_OK
    session = AuthSession.objects.get(user=user)
    assert session.refresh_jti
    assert session.device_label == "Chrome browser"
    assert session.ip_address == "203.0.113.10"
    assert session.request_id == "auth-session-login-1"
    assert session.fingerprint_hash
    login_calls = [
        call.kwargs
        for call in mock_task.delay.call_args_list
        if call.kwargs.get("action") == audit_actions.LOGIN_SUCCESS
    ]
    assert login_calls[0]["extra_data"]["session_id"] == session.pk


def test_user_can_list_and_revoke_own_session() -> None:
    """User session endpoints should list and revoke own sessions only."""
    user = UserFactory(email="owner-session@example.com", is_email_verified=True)
    client = APIClient()
    login_response = client.post(
        reverse("authentication:login-password"),
        data={"identifier": user.email, "pass" + "word": "StrongPass!234"},
        format="json",
    )
    session = AuthSession.objects.get(user=user)
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login_response.data['data']['tokens']['access']}"
    )

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        list_response = client.get(reverse("authentication:session-list"))
        revoke_response = client.post(
            reverse("authentication:session-revoke", kwargs={"session_id": session.pk})
        )

    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data["data"]["count"] == 1
    assert revoke_response.status_code == status.HTTP_200_OK
    session.refresh_from_db()
    assert session.is_revoked is True
    assert session.revoked_by == user
    assert BlacklistedToken.objects.filter(token__jti=session.refresh_jti).exists()
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.AUTH_SESSION_REVOKED in called_actions


def test_user_cannot_revoke_other_user_session() -> None:
    """Session revoke endpoint must be IDOR-safe."""
    owner = UserFactory(email="session-owner@example.com", is_email_verified=True)
    other = UserFactory(email="session-other@example.com", is_email_verified=True)
    other_refresh = RefreshToken.for_user(other)
    other_session = AuthSession.objects.create(
        user=other,
        refresh_jti=str(other_refresh["jti"]),
        fingerprint_hash=AuthSession.build_fingerprint_hash(
            user_agent="other", ip_address="127.0.0.1"
        ),
    )
    client = _jwt_client(owner)

    response = client.post(
        reverse("authentication:session-revoke", kwargs={"session_id": other_session.pk})
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    other_session.refresh_from_db()
    assert other_session.is_revoked is False


def test_admin_can_list_and_revoke_all_user_sessions() -> None:
    """Admin should list and revoke all active sessions for a target user."""
    admin = AdminUserFactory()
    user = UserFactory(email="admin-target@example.com", is_email_verified=True)
    for _index in range(2):
        refresh = RefreshToken.for_user(user)
        AuthSession.objects.create(
            user=user,
            refresh_jti=str(refresh["jti"]),
            fingerprint_hash=AuthSession.build_fingerprint_hash(
                user_agent="admin-test", ip_address="127.0.0.1"
            ),
        )
    client = _jwt_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        list_response = client.get(
            reverse("authentication:admin-user-session-list", kwargs={"user_id": user.pk})
        )
        revoke_response = client.post(
            reverse("authentication:admin-user-session-revoke-all", kwargs={"user_id": user.pk})
        )

    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data["data"]["count"] == 2
    assert revoke_response.status_code == status.HTTP_200_OK
    assert revoke_response.data["data"]["revoked_count"] == 2
    assert AuthSession.objects.filter(user=user, is_revoked=True, revoked_by=admin).count() == 2
    assert BlacklistedToken.objects.filter(token__user=user).count() == 2
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.AUTH_USER_SESSIONS_REVOKED in called_actions


def test_logout_revokes_matching_tracked_session() -> None:
    """Logout should blacklist refresh token and revoke matching AuthSession row."""
    user = UserFactory(email="logout-session@example.com", is_email_verified=True)
    client = APIClient()
    login_response = client.post(
        reverse("authentication:login-password"),
        data={"identifier": user.email, "pass" + "word": "StrongPass!234"},
        format="json",
    )
    refresh = login_response.data["data"]["tokens"]["refresh"]
    access = login_response.data["data"]["tokens"]["access"]
    session = AuthSession.objects.get(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = client.post(
        reverse("authentication:logout"), data={"refresh": refresh}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    session.refresh_from_db()
    assert session.is_revoked is True
    assert OutstandingToken.objects.filter(jti=session.refresh_jti).exists()
    assert BlacklistedToken.objects.filter(token__jti=session.refresh_jti).exists()
