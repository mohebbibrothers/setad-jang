"""R4J C1 evidence chain-of-custody tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.r4j.choices import EvidenceCustodyEventType
from apps.r4j.models import R4JEvidenceCustodyEvent
from apps.r4j.services import add_attachment, submit_report
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.r4j import R4JCriminalFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _file(name: str = "evidence.pdf", content: bytes = b"evidence-bytes") -> SimpleUploadedFile:
    """Build in-memory evidence file."""
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _admin_client(admin_user=None) -> APIClient:
    """Build JWT-authenticated admin client."""
    user = admin_user or AdminUserFactory()
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def test_criminal_attachment_is_hashed_and_custody_events_created() -> None:
    """Admin evidence attachment should get SHA-256 hash and uploaded/hashed custody events."""
    admin = AdminUserFactory()
    criminal = R4JCriminalFactory()

    attachment = add_attachment(
        criminal=criminal,
        file=_file(content=b"criminal-evidence"),
        title="سند شاهد",
        uploaded_by=admin,
    )

    assert len(attachment.file_sha256) == 64
    assert attachment.file_size == len(b"criminal-evidence")
    events = list(attachment.custody_events.order_by("created_at"))
    assert [event.event_type for event in events] == [EvidenceCustodyEventType.UPLOADED, EvidenceCustodyEventType.HASHED]
    assert all(event.file_sha256 == attachment.file_sha256 for event in events)


def test_report_attachment_is_hashed_and_custody_events_created() -> None:
    """User report attachments should also receive evidence hashes and custody events."""
    user = UserFactory()
    criminal = R4JCriminalFactory()

    report = submit_report(
        criminal=criminal,
        submitted_by=user,
        field_changes=[{"field_name": "first_name", "suggested_value": "NewName"}],
        attachments=[{"file": _file(content=b"report-evidence"), "title": "گزارش", "kind": "document"}],
    )
    attachment = report.attachments.get()

    assert len(attachment.file_sha256) == 64
    assert attachment.file_size == len(b"report-evidence")
    assert attachment.custody_events.count() == 2


def test_custody_event_is_append_only() -> None:
    """Custody events should reject mutation and deletion."""
    attachment = add_attachment(criminal=R4JCriminalFactory(), file=_file(), title="سند")
    event = attachment.custody_events.first()

    event.note = "tamper"
    with pytest.raises(PermissionError):
        event.save()
    with pytest.raises(PermissionError):
        event.delete()


def test_admin_can_append_custody_review_event_with_audit() -> None:
    """Admin API should append custody review event and audit the action."""
    admin = AdminUserFactory()
    attachment = add_attachment(criminal=R4JCriminalFactory(), file=_file(), title="سند", uploaded_by=admin)
    event = attachment.custody_events.first()
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse("r4j:admin-evidence-custody-review", kwargs={"event_id": event.pk}),
            data={"event_type": EvidenceCustodyEventType.REVIEWED, "note": "بررسی شد"},
            format="json",
        )

    assert response.status_code == status.HTTP_201_CREATED
    assert R4JEvidenceCustodyEvent.objects.filter(
        criminal_attachment=attachment,
        event_type=EvidenceCustodyEventType.REVIEWED,
        note="بررسی شد",
    ).exists()
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.R4J_EVIDENCE_CUSTODY_REVIEWED in called_actions


def test_admin_custody_list_endpoint_returns_events() -> None:
    """Admin custody list endpoint should expose paginated custody events."""
    add_attachment(criminal=R4JCriminalFactory(), file=_file(), title="سند")
    client = _admin_client()

    response = client.get(reverse("r4j:admin-evidence-custody-list"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["count"] == 2
