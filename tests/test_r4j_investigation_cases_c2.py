"""R4J C2 investigation case management tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.r4j.choices import (
    InvestigationCaseEventType,
    InvestigationCasePriority,
    InvestigationCaseSeverity,
    InvestigationCaseStatus,
)
from apps.r4j.models import R4JCaseEvent
from apps.r4j.services import (
    InvestigationCaseLocked,
    assign_investigation_case,
    close_investigation_case,
    create_investigation_case_from_report,
    reopen_investigation_case,
    triage_investigation_case,
)
from tests.factories.auth import AdminUserFactory
from tests.factories.r4j import (
    R4JReportAttachmentFactory,
    R4JReportFactory,
    R4JReportFieldChangeFactory,
)

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def test_case_created_from_report_has_number_score_due_dates_and_event() -> None:
    """A report should become a numbered operational case with immutable timeline."""
    admin = AdminUserFactory()
    report = R4JReportFactory(notes="اطلاعات تکمیلی")
    R4JReportFieldChangeFactory(report=report, field_name="city")
    R4JReportAttachmentFactory(report=report)

    case = create_investigation_case_from_report(report=report, actor=admin)

    assert case.case_number.startswith("R4J-")
    assert case.status == InvestigationCaseStatus.NEW
    assert case.evidence_completeness_score >= 30
    assert case.first_response_due_at is not None
    assert case.resolution_due_at is not None
    assert case.events.filter(event_type=InvestigationCaseEventType.CREATED).exists()


def test_case_timeline_is_append_only() -> None:
    """Operational timeline events should reject mutation and deletion."""
    case = create_investigation_case_from_report(report=R4JReportFactory(), actor=AdminUserFactory())
    event = case.events.get(event_type=InvestigationCaseEventType.CREATED)

    event.note = "tamper"
    with pytest.raises(PermissionError):
        event.save()
    with pytest.raises(PermissionError):
        event.delete()


def test_case_triage_and_assignment_write_events() -> None:
    """Triage and assignment should update state through services and append events."""
    admin = AdminUserFactory()
    assignee = AdminUserFactory()
    case = create_investigation_case_from_report(report=R4JReportFactory(), actor=admin)

    case = triage_investigation_case(
        case=case,
        actor=admin,
        priority=InvestigationCasePriority.HIGH,
        severity=InvestigationCaseSeverity.HIGH,
        note="اولویت بالا",
    )
    case = assign_investigation_case(case=case, actor=admin, assignee=assignee, note="ارجاع به کارشناس")

    assert case.status == InvestigationCaseStatus.ASSIGNED
    assert case.assigned_to == assignee
    assert R4JCaseEvent.objects.filter(case=case, event_type=InvestigationCaseEventType.TRIAGED).exists()
    assert R4JCaseEvent.objects.filter(case=case, event_type=InvestigationCaseEventType.ASSIGNED).exists()


def test_closed_case_cannot_be_assigned_until_reopened() -> None:
    """Terminal cases should be locked unless they are explicitly reopened."""
    admin = AdminUserFactory()
    assignee = AdminUserFactory()
    case = create_investigation_case_from_report(report=R4JReportFactory(), actor=admin)
    case = close_investigation_case(case=case, actor=admin, reason="تکمیل بررسی")

    with pytest.raises(InvestigationCaseLocked):
        assign_investigation_case(case=case, actor=admin, assignee=assignee)

    case = reopen_investigation_case(case=case, actor=admin, reason="مدرک جدید")
    case = assign_investigation_case(case=case, actor=admin, assignee=assignee)

    assert case.status == InvestigationCaseStatus.ASSIGNED
    assert case.events.filter(event_type=InvestigationCaseEventType.REOPENED).exists()


def test_admin_create_case_endpoint_audits_sensitive_action() -> None:
    """Admin case creation endpoint should audit the sensitive action."""
    admin = AdminUserFactory()
    report = R4JReportFactory()
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse("r4j:admin-case-create-from-report", kwargs={"report_id": report.pk}),
            data={},
            format="json",
        )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["data"]["case_number"].startswith("R4J-")
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.R4J_CASE_CREATED in called_actions


def test_admin_case_workflow_endpoints_and_overview() -> None:
    """Admin APIs should expose workflow actions, timeline, and operations overview."""
    admin = AdminUserFactory()
    assignee = AdminUserFactory()
    case = create_investigation_case_from_report(report=R4JReportFactory(), actor=admin)
    client = _admin_client(admin)

    triage_response = client.post(
        reverse("r4j:admin-case-triage", kwargs={"case_number": case.case_number}),
        data={"priority": InvestigationCasePriority.HIGH, "severity": InvestigationCaseSeverity.HIGH, "note": "فوری"},
        format="json",
    )
    assign_response = client.post(
        reverse("r4j:admin-case-assign", kwargs={"case_number": case.case_number}),
        data={"assignee_id": assignee.pk, "note": "ارجاع"},
        format="json",
    )
    timeline_response = client.get(reverse("r4j:admin-case-timeline", kwargs={"case_number": case.case_number}))
    overview_response = client.get(reverse("r4j:admin-case-operations-overview"))

    assert triage_response.status_code == status.HTTP_200_OK
    assert assign_response.status_code == status.HTTP_200_OK
    assert assign_response.data["data"]["assigned_to"] == assignee.pk
    assert timeline_response.status_code == status.HTTP_200_OK
    assert len(timeline_response.data["data"]) >= 3
    assert overview_response.status_code == status.HTTP_200_OK
    assert overview_response.data["data"]["total_cases"] >= 1
