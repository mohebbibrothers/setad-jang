"""Support Desk Phase 4 admin API, taxonomy and operations tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.support_desk.choices import DuplicateReviewStatus, TicketStatus
from apps.support_desk.models import (
    SupportDuplicateCandidate,
    SupportTicketMessage,
    SupportTicketType,
)
from apps.support_desk.services import create_ticket, submit_ticket
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.support_desk import (
    SupportCategoryFactory,
    SupportDepartmentFactory,
    SupportTicketFactory,
    SupportTicketTypeFactory,
)

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestSupportAdminPermissions:
    """Admin boundary smoke tests."""

    def test_regular_user_cannot_access_admin_ticket_queue(self) -> None:
        response = _client_for(UserFactory()).get(reverse("support_desk:admin-ticket-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestSupportAdminTaxonomyAPI:
    """Admin taxonomy endpoints for dynamic departments/categories/types/SLA/macros."""

    def test_admin_can_create_update_and_deactivate_department_with_audit(self) -> None:
        client = _client_for(AdminUserFactory())

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            create_response = client.post(
                reverse("support_desk:admin-department-list-create"),
                data={"title": "پشتیبانی ویژه", "description": "VIP", "order": 50},
                format="json",
            )

        assert create_response.status_code == status.HTTP_201_CREATED
        department_id = create_response.data["data"]["id"]
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.SUPPORT_DEPARTMENT_CREATED

        update_response = client.patch(
            reverse("support_desk:admin-department-detail", kwargs={"department_id": department_id}),
            data={"title": "پشتیبانی ویژه اصلاح‌شده"},
            format="json",
        )
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.data["data"]["title"] == "پشتیبانی ویژه اصلاح‌شده"

        delete_response = client.delete(reverse("support_desk:admin-department-detail", kwargs={"department_id": department_id}))
        assert delete_response.status_code == status.HTTP_200_OK
        assert delete_response.data["data"]["is_active"] is False

    def test_admin_can_create_move_and_deactivate_tree_category(self) -> None:
        department = SupportDepartmentFactory(title="دپارتمان درخت")
        root = SupportCategoryFactory(department=department, title="ریشه درخت")
        client = _client_for(AdminUserFactory())

        create_response = client.post(
            reverse("support_desk:admin-category-list-create"),
            data={"department_id": department.pk, "parent_id": root.pk, "title": "زیرشاخه درخت", "order": 2},
            format="json",
        )

        assert create_response.status_code == status.HTTP_201_CREATED
        child_id = create_response.data["data"]["id"]
        assert create_response.data["data"]["depth"] == 1

        move_response = client.patch(
            reverse("support_desk:admin-category-detail", kwargs={"category_id": child_id}),
            data={"department_id": department.pk, "parent_id": None, "title": "زیرشاخه مستقل"},
            format="json",
        )
        assert move_response.status_code == status.HTTP_200_OK
        assert move_response.data["data"]["depth"] == 0

        delete_response = client.delete(reverse("support_desk:admin-category-detail", kwargs={"category_id": child_id}))
        assert delete_response.status_code == status.HTTP_200_OK
        assert delete_response.data["data"]["is_active"] is False

    def test_admin_can_manage_ticket_type_sla_policy_and_canned_response(self) -> None:
        department = SupportDepartmentFactory(title="عملیات ادمین")
        category = SupportCategoryFactory(department=department, title="دسته عملیات")
        client = _client_for(AdminUserFactory())

        sla_response = client.post(
            reverse("support_desk:admin-sla-policy-list-create"),
            data={"title": "SLA عملیات", "department_id": department.pk, "priority": "high", "severity": "major", "first_response_minutes": 30, "resolution_minutes": 120},
            format="json",
        )
        assert sla_response.status_code == status.HTTP_201_CREATED
        sla_id = sla_response.data["data"]["id"]

        type_response = client.post(
            reverse("support_desk:admin-ticket-type-list-create"),
            data={"code": "ops-special", "title": "عملیات ویژه", "default_department_id": department.pk, "default_category_id": category.pk, "default_sla_policy_id": sla_id, "default_priority": "high", "default_severity": "major"},
            format="json",
        )
        assert type_response.status_code == status.HTTP_201_CREATED
        assert SupportTicketType.objects.filter(code="ops-special").exists()

        canned_response = client.post(
            reverse("support_desk:admin-canned-response-list-create"),
            data={"department_id": department.pk, "category_id": category.pk, "title": "پاسخ عملیات", "body": "پاسخ آماده عملیات"},
            format="json",
        )
        assert canned_response.status_code == status.HTTP_201_CREATED
        canned_id = canned_response.data["data"]["id"]

        use_response = client.post(reverse("support_desk:admin-canned-response-use", kwargs={"canned_response_id": canned_id}))
        assert use_response.status_code == status.HTTP_200_OK
        assert use_response.data["data"]["usage_count"] == 1


class TestSupportAdminTicketOperationsAPI:
    """Admin ticket queue/detail and operational actions."""

    def test_admin_queue_detail_reply_internal_note_assign_status_and_escalate(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.SUBMITTED)
        admin = AdminUserFactory()
        assignee = AdminUserFactory(email="support-assignee@test.local")
        department = SupportDepartmentFactory(title="ارجاع API")
        client = _client_for(admin)

        list_response = client.get(reverse("support_desk:admin-ticket-list"), data={"status": TicketStatus.SUBMITTED})
        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["data"]["count"] >= 1

        reply_response = client.post(
            reverse("support_desk:admin-ticket-reply", kwargs={"ticket_number": ticket.ticket_number}),
            data={"body": "پاسخ ادمین"},
            format="json",
        )
        assert reply_response.status_code == status.HTTP_201_CREATED

        note_response = client.post(
            reverse("support_desk:admin-ticket-internal-note", kwargs={"ticket_number": ticket.ticket_number}),
            data={"body": "یادداشت داخلی محرمانه"},
            format="json",
        )
        assert note_response.status_code == status.HTTP_201_CREATED
        assert note_response.data["data"]["is_internal"] is True

        assign_response = client.post(
            reverse("support_desk:admin-ticket-assign", kwargs={"ticket_number": ticket.ticket_number}),
            data={"assignee_id": assignee.pk, "department_id": department.pk, "reason": "ارجاع تخصصی"},
            format="json",
        )
        assert assign_response.status_code == status.HTTP_200_OK
        assert assign_response.data["data"]["assigned_to_id"] == assignee.pk

        status_response = client.post(
            reverse("support_desk:admin-ticket-status", kwargs={"ticket_number": ticket.ticket_number}),
            data={"status": TicketStatus.IN_PROGRESS, "reason": "شروع بررسی"},
            format="json",
        )
        assert status_response.status_code == status.HTTP_200_OK
        assert status_response.data["data"]["status"] == TicketStatus.IN_PROGRESS

        escalate_response = client.post(
            reverse("support_desk:admin-ticket-escalate", kwargs={"ticket_number": ticket.ticket_number}),
            data={"reason": "فوری"},
            format="json",
        )
        assert escalate_response.status_code == status.HTTP_200_OK
        assert escalate_response.data["data"]["status"] == TicketStatus.ESCALATED

        detail_response = client.get(reverse("support_desk:admin-ticket-detail", kwargs={"ticket_number": ticket.ticket_number}))
        assert detail_response.status_code == status.HTTP_200_OK
        bodies = [message["body"] for message in detail_response.data["data"]["messages"]]
        assert "یادداشت داخلی محرمانه" in bodies

    def test_admin_can_review_duplicate_candidate(self) -> None:
        owner = UserFactory()
        ticket_type = SupportTicketTypeFactory()
        first = create_ticket(owner=owner, ticket_type=ticket_type, subject="پرداخت ثبت نشده", description="پرداخت انجام شده اما ثبت نشده")
        second = create_ticket(owner=owner, ticket_type=ticket_type, subject="پرداخت ثبت نشده", description="پرداخت انجام شده اما ثبت نشده")
        duplicate = SupportDuplicateCandidate.objects.get(ticket=second, candidate_ticket=first)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(AdminUserFactory()).post(
                reverse("support_desk:admin-duplicate-review", kwargs={"duplicate_id": duplicate.pk}),
                data={"status": DuplicateReviewStatus.CONFIRMED, "reason": "تکراری قطعی"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        duplicate.refresh_from_db()
        assert duplicate.status == DuplicateReviewStatus.CONFIRMED
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.SUPPORT_DUPLICATE_REVIEWED

    def test_department_with_open_ticket_cannot_be_deactivated(self) -> None:
        ticket_type = SupportTicketTypeFactory()
        ticket = create_ticket(owner=UserFactory(), ticket_type=ticket_type, subject="باز", description="تیکت باز برای guard")
        submit_ticket(ticket=ticket, user=ticket.owner)

        response = _client_for(AdminUserFactory()).delete(
            reverse("support_desk:admin-department-detail", kwargs={"department_id": ticket.department_id})
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_admin_close_endpoint_closes_resolved_ticket(self) -> None:
        ticket = SupportTicketFactory(status=TicketStatus.RESOLVED)
        response = _client_for(AdminUserFactory()).post(
            reverse("support_desk:admin-ticket-close", kwargs={"ticket_number": ticket.ticket_number}),
            data={"reason": "بستن توسط ادمین"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == TicketStatus.CLOSED
        assert SupportTicketMessage.objects.filter(ticket__ticket_number=ticket.ticket_number, message_type="status_change").exists()
