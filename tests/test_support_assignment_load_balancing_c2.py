"""Support C2 assignment load-balancing tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.support_desk.choices import TicketPriority, TicketSeverity, TicketStatus
from apps.support_desk.models import SupportTicketAssignment
from apps.support_desk.services import get_support_assignment_recommendation
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.support_desk import SupportDepartmentFactory, SupportTicketFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated support admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def _open_ticket(*, department, assignee=None, priority=TicketPriority.NORMAL, severity=TicketSeverity.MINOR, status_value=TicketStatus.OPEN):
    """Create an open support ticket for workload calculations."""
    return SupportTicketFactory(
        owner=UserFactory(),
        department=department,
        assigned_to=assignee,
        status=status_value,
        priority=priority,
        severity=severity,
    )


def test_assignment_recommendation_prefers_least_loaded_agent() -> None:
    """Recommendation should select the active support admin with lowest weighted workload."""
    department = SupportDepartmentFactory()
    overloaded = AdminUserFactory(email="overloaded@test.local")
    least_loaded = AdminUserFactory(email="least@test.local")
    _open_ticket(department=department, assignee=overloaded)
    _open_ticket(department=department, assignee=overloaded, priority=TicketPriority.URGENT, severity=TicketSeverity.CRITICAL)
    target = _open_ticket(department=department, assignee=None, status_value=TicketStatus.SUBMITTED)

    recommendation = get_support_assignment_recommendation(ticket=target)

    assert recommendation.recommended_assignee == least_loaded
    assert recommendation.candidates[0].user == least_loaded
    assert recommendation.candidates[0].workload_score < recommendation.candidates[-1].workload_score
    assert "least_loaded_score" in recommendation.reason_codes


def test_assignment_recommendation_considers_department_default_assignee_bonus() -> None:
    """Department default assignee should receive a transparent tie-break bonus."""
    default_agent = AdminUserFactory(email="default-support@test.local")
    department = SupportDepartmentFactory(default_assignee=default_agent)
    target = _open_ticket(department=department, assignee=None, status_value=TicketStatus.SUBMITTED)

    recommendation = get_support_assignment_recommendation(ticket=target)

    assert recommendation.recommended_assignee == default_agent
    assert "department_default_assignee_considered" in recommendation.reason_codes
    assert "department_default_assignee_bonus" in recommendation.candidates[0].reason_codes


def test_assignment_recommendation_endpoint_audits_sensitive_operational_read() -> None:
    """Admin recommendation endpoint should return candidates and audit recommendation generation."""
    admin = AdminUserFactory()
    SupportDepartmentFactory(default_assignee=admin)
    ticket = _open_ticket(department=SupportDepartmentFactory(), assignee=None, status_value=TicketStatus.SUBMITTED)
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.get(reverse("support_desk:admin-ticket-assignment-recommendation", kwargs={"ticket_number": ticket.ticket_number}))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["ticket_number"] == ticket.ticket_number
    assert response.data["data"]["policy_version"] == "support-assignment-load-balancing/v1"
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.SUPPORT_ASSIGNMENT_RECOMMENDED in called_actions


def test_auto_assign_endpoint_applies_recommendation_and_audits_assignment() -> None:
    """Auto-assign endpoint should assign to least-loaded agent and record assignment history."""
    admin = AdminUserFactory(email="request-admin@test.local")
    department = SupportDepartmentFactory()
    busy = AdminUserFactory(email="busy@test.local")
    least_loaded = AdminUserFactory(email="auto-target@test.local")
    _open_ticket(department=department, assignee=admin)
    _open_ticket(department=department, assignee=busy, priority=TicketPriority.URGENT, severity=TicketSeverity.CRITICAL)
    ticket = _open_ticket(department=department, assignee=None, status_value=TicketStatus.SUBMITTED)
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse("support_desk:admin-ticket-auto-assign", kwargs={"ticket_number": ticket.ticket_number}),
            data={"department_id": department.pk, "reason": "ارجاع خودکار تست"},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK
    ticket.refresh_from_db()
    assert ticket.assigned_to == least_loaded
    assert SupportTicketAssignment.objects.filter(ticket=ticket, assigned_to=least_loaded).exists()
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.SUPPORT_TICKET_ASSIGNED in called_actions
