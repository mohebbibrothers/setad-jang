"""Support Desk Phase 3 user API tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.support_desk.choices import TicketStatus
from apps.support_desk.models import SupportTicketAttachment, SupportTicketMessage
from apps.support_desk.services import (
    add_admin_reply,
    add_internal_note,
    close_ticket,
    resolve_ticket,
)
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.support_desk import SupportTicketFactory, SupportTicketTypeFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestSupportTaxonomyAPI:
    """Authenticated taxonomy browse endpoints."""

    def test_authenticated_user_can_browse_departments_categories_and_ticket_types(self) -> None:
        client = _client_for(UserFactory())

        departments = client.get(reverse("support_desk:department-list"))
        categories = client.get(reverse("support_desk:category-list"))
        ticket_types = client.get(reverse("support_desk:ticket-type-list"))

        assert departments.status_code == status.HTTP_200_OK
        assert categories.status_code == status.HTTP_200_OK
        assert ticket_types.status_code == status.HTTP_200_OK
        assert departments.data["data"]
        assert categories.data["data"]
        assert ticket_types.data["data"]

    def test_anonymous_user_cannot_browse_support_taxonomy(self) -> None:
        response = APIClient().get(reverse("support_desk:department-list"))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestSupportUserTicketAPI:
    """User ticket lifecycle APIs."""

    def test_user_can_create_update_submit_and_filter_own_ticket(self) -> None:
        user = UserFactory()
        ticket_type = SupportTicketTypeFactory(title="نوع API")
        client = _client_for(user)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            create_response = client.post(
                reverse("support_desk:user-ticket-list-create"),
                data={
                    "ticket_type_id": ticket_type.pk,
                    "subject": "مشکل پرداخت سایت",
                    "description": "پرداخت انجام شده اما در سایت ثبت نشده است",
                },
                format="json",
            )

        assert create_response.status_code == status.HTTP_201_CREATED
        ticket_number = create_response.data["data"]["ticket_number"]
        assert create_response.data["data"]["status"] == TicketStatus.DRAFT
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.SUPPORT_TICKET_CREATED

        update_response = client.patch(
            reverse("support_desk:user-ticket-detail", kwargs={"ticket_number": ticket_number}),
            data={
                "ticket_type_id": ticket_type.pk,
                "subject": "مشکل پرداخت مددکار",
                "description": "پرداخت انجام شده ولی ثبت نشده است",
            },
            format="json",
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.data["data"]["subject"] == "مشکل پرداخت مددکار"

        submit_response = client.post(
            reverse("support_desk:user-ticket-submit", kwargs={"ticket_number": ticket_number})
        )
        assert submit_response.status_code == status.HTTP_200_OK
        assert submit_response.data["data"]["status"] == TicketStatus.SUBMITTED
        assert submit_response.data["data"]["first_response_due_at"] is not None

        list_response = client.get(
            reverse("support_desk:user-ticket-list-create"), data={"search": "مددکار"}
        )
        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["data"]["count"] == 1

    def test_user_cannot_access_other_user_ticket(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)
        other = UserFactory()

        response = _client_for(other).get(
            reverse(
                "support_desk:user-ticket-detail", kwargs={"ticket_number": ticket.ticket_number}
            )
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_submitted_ticket_cannot_be_edited_by_user(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)

        response = _client_for(ticket.owner).patch(
            reverse(
                "support_desk:user-ticket-detail", kwargs={"ticket_number": ticket.ticket_number}
            ),
            data={
                "ticket_type_id": ticket.ticket_type_id,
                "subject": "ویرایش غیرمجاز",
                "description": "بعد از ارسال نباید ویرایش شود",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestSupportConversationTimelineAndAttachmentsAPI:
    """Reply, timeline, internal-note privacy and attachment APIs."""

    def test_user_reply_and_timeline_never_expose_internal_notes(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)
        admin = AdminUserFactory()
        add_admin_reply(ticket=ticket, admin=admin, body="لطفاً شماره پیگیری را ارسال کنید")
        add_internal_note(
            ticket=ticket, admin=admin, body="این یادداشت نباید به کاربر نمایش داده شود"
        )

        reply_response = _client_for(ticket.owner).post(
            reverse(
                "support_desk:user-ticket-reply", kwargs={"ticket_number": ticket.ticket_number}
            ),
            data={"body": "شماره پیگیری ۱۲۳۴"},
            format="json",
        )
        timeline_response = _client_for(ticket.owner).get(
            reverse(
                "support_desk:user-ticket-timeline", kwargs={"ticket_number": ticket.ticket_number}
            )
        )

        assert reply_response.status_code == status.HTTP_201_CREATED
        assert timeline_response.status_code == status.HTTP_200_OK
        bodies = [row["body"] for row in timeline_response.data["data"]]
        assert "این یادداشت نباید به کاربر نمایش داده شود" not in bodies
        assert all(row["message_type"] != "internal_note" for row in timeline_response.data["data"])

    def test_user_can_upload_public_attachment(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)
        upload = SimpleUploadedFile("evidence.txt", b"payment receipt", content_type="text/plain")

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(ticket.owner).post(
                reverse(
                    "support_desk:user-ticket-attachment",
                    kwargs={"ticket_number": ticket.ticket_number},
                ),
                data={"file": upload, "attachment_kind": "document"},
                format="multipart",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert SupportTicketAttachment.objects.filter(ticket=ticket, visibility="public").exists()
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.SUPPORT_ATTACHMENT_ADDED


class TestSupportSuggestReopenAndSatisfactionAPI:
    """Smart suggest, reopen and satisfaction endpoints."""

    def test_suggest_endpoint_returns_payment_triage(self) -> None:
        user = UserFactory()

        response = _client_for(user).post(
            reverse("support_desk:user-ticket-suggest"),
            data={"subject": "پرداخت ثبت نشده", "description": "پرداخت انجام شده اما ثبت نشده است"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["priority"] == "high"
        assert "payment_keyword_priority_boost" in response.data["data"]["reason_codes"]

    def test_user_can_rate_and_reopen_resolved_ticket(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)
        admin = AdminUserFactory()
        resolve_ticket(ticket=ticket, admin=admin, reason="حل شد")

        satisfaction_response = _client_for(ticket.owner).post(
            reverse(
                "support_desk:user-ticket-satisfaction",
                kwargs={"ticket_number": ticket.ticket_number},
            ),
            data={"rating": 5, "comment": "خوب بود"},
            format="json",
        )
        assert satisfaction_response.status_code == status.HTTP_201_CREATED

        close_ticket(ticket=ticket, actor=ticket.owner, reason="تأیید")
        reopen_response = _client_for(ticket.owner).post(
            reverse(
                "support_desk:user-ticket-reopen", kwargs={"ticket_number": ticket.ticket_number}
            ),
            data={"reason": "مشکل برگشت"},
            format="json",
        )

        assert reopen_response.status_code == status.HTTP_200_OK
        assert reopen_response.data["data"]["status"] == TicketStatus.REOPENED

    def test_user_cannot_rate_unresolved_ticket(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)

        response = _client_for(ticket.owner).post(
            reverse(
                "support_desk:user-ticket-satisfaction",
                kwargs={"ticket_number": ticket.ticket_number},
            ),
            data={"rating": 5},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert (
            SupportTicketMessage.objects.filter(ticket=ticket, message_type="internal_note").count()
            == 0
        )
