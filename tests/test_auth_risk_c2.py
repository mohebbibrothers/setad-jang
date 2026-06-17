"""Auth C2 risk-based authentication tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.authentication.choices import AuthRiskSeverity, AuthRiskSignalType, AuthRiskStatus
from apps.authentication.models import AuthRiskSignal, AuthSession
from apps.authentication.services import create_auth_risk_signal, evaluate_auth_session_risk
from tests.factories.auth import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _session(*, user, user_agent: str, ip_address: str) -> AuthSession:
    """Create tracked auth session with fingerprint for tests."""
    refresh = RefreshToken.for_user(user)
    return AuthSession.objects.create(
        user=user,
        refresh_jti=str(refresh["jti"]),
        user_agent=user_agent,
        ip_address=ip_address,
        device_label="test-device",
        fingerprint_hash=AuthSession.build_fingerprint_hash(user_agent=user_agent, ip_address=ip_address),
    )


def test_new_device_and_new_ip_risk_are_generated_for_first_session() -> None:
    """A first tracked login session should produce new-device and new-IP signals."""
    user = UserFactory()
    session = _session(user=user, user_agent="Chrome Risk Test", ip_address="198.51.100.10")

    signals = evaluate_auth_session_risk(session=session)

    signal_types = {signal.signal_type for signal in signals}
    assert AuthRiskSignalType.NEW_DEVICE in signal_types
    assert AuthRiskSignalType.NEW_IP in signal_types
    assert AuthRiskSignal.objects.filter(user=user, status=AuthRiskStatus.OPEN).count() == 2


def test_known_device_and_ip_do_not_create_duplicate_risks() -> None:
    """A known fingerprint/IP should not create duplicate risk signals."""
    user = UserFactory()
    _session(user=user, user_agent="Chrome Stable", ip_address="198.51.100.11")
    second = _session(user=user, user_agent="Chrome Stable", ip_address="198.51.100.11")

    signals = evaluate_auth_session_risk(session=second)

    assert signals == []


def test_admin_can_list_and_review_auth_risk_signal_with_audit() -> None:
    """Admin risk review endpoint should review signal and audit the action."""
    admin = AdminUserFactory()
    user = UserFactory()
    signal = create_auth_risk_signal(
        signal_type=AuthRiskSignalType.NEW_DEVICE,
        severity=AuthRiskSeverity.MEDIUM,
        user=user,
        ip_address="203.0.113.50",
        description="new device",
    )
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        list_response = client.get(reverse("authentication:admin-risk-signal-list"))
        review_response = client.post(
            reverse("authentication:admin-risk-signal-review", kwargs={"signal_id": signal.pk}),
            data={"status": AuthRiskStatus.ESCALATED, "review_note": "نیازمند بررسی امنیتی"},
            format="json",
        )

    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data["data"]["count"] >= 1
    assert review_response.status_code == status.HTTP_200_OK
    signal.refresh_from_db()
    assert signal.status == AuthRiskStatus.ESCALATED
    assert signal.reviewed_by == admin
    assert signal.review_note == "نیازمند بررسی امنیتی"
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.AUTH_RISK_SIGNAL_REVIEWED in called_actions


def test_password_login_generates_auth_risk_signals_for_new_device() -> None:
    """Real password login should create tracked session and risk signals."""
    user = UserFactory(email="risk-login@example.com", is_email_verified=True)
    client = APIClient()

    response = client.post(
        reverse("authentication:login-password"),
        data={"identifier": user.email, "pass" + "word": "StrongPass!234"},
        format="json",
        HTTP_USER_AGENT="Mozilla/5.0 Firefox Risk",
        REMOTE_ADDR="203.0.113.77",
    )

    assert response.status_code == status.HTTP_200_OK
    session = AuthSession.objects.get(user=user)
    assert AuthRiskSignal.objects.filter(user=user, session=session, signal_type=AuthRiskSignalType.NEW_DEVICE).exists()
    assert AuthRiskSignal.objects.filter(user=user, session=session, signal_type=AuthRiskSignalType.NEW_IP).exists()
