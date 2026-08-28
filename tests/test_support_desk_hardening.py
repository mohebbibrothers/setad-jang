"""Support Desk Phase 6 final polish and performance contracts.

این تست‌ها guard نهایی اپ تیکت هستند:
- selector/serializerهای پرترافیک نباید N+1 query تولید کنند.
- مرز privacy بین user timeline و admin timeline باید ثابت بماند.
- permission boundary و route contractهای اصلی smoke-test می‌شوند.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.support_desk import selectors
from apps.support_desk.choices import TicketStatus
from apps.support_desk.serializers import (
    SupportAdminTicketDetailSerializer,
    SupportTicketDetailSerializer,
    SupportTicketTypeSerializer,
)
from apps.support_desk.services import (
    add_admin_reply,
    add_internal_note,
    create_ticket,
    submit_ticket,
)
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.support_desk import SupportTicketTypeFactory

pytestmark = pytest.mark.django_db


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _make_submitted_ticket():
    """Create a submitted ticket with public and internal timeline entries."""
    admin = AdminUserFactory()
    ticket_type = SupportTicketTypeFactory(title="Performance Type")
    ticket = create_ticket(
        owner=UserFactory(),
        ticket_type=ticket_type,
        subject="مشکل پرداخت حرفه‌ای",
        description="پرداخت انجام شده اما ثبت نشده است",
    )
    submit_ticket(ticket=ticket, user=ticket.owner)
    add_admin_reply(ticket=ticket, admin=admin, body="پاسخ عمومی ادمین")
    add_internal_note(ticket=ticket, admin=admin, body="یادداشت داخلی محرمانه")
    return ticket


class TestSupportQueryPerformanceContracts:
    """N+1 regression contracts for support selectors and serializers."""

    def test_user_ticket_detail_serializer_does_not_query_after_user_selector(self) -> None:
        ticket = _make_submitted_ticket()
        prefetched = selectors.get_user_ticket_by_number(
            user_id=ticket.owner_id, ticket_number=ticket.ticket_number
        )

        with CaptureQueriesContext(connection) as captured:
            data = SupportTicketDetailSerializer(prefetched).data

        assert data["ticket_number"] == ticket.ticket_number
        assert all(message["message_type"] != "internal_note" for message in data["messages"])
        assert len(captured) == 0

    def test_admin_ticket_detail_serializer_does_not_query_after_admin_selector(self) -> None:
        ticket = _make_submitted_ticket()
        prefetched = selectors.get_admin_ticket_by_number(ticket_number=ticket.ticket_number)

        with CaptureQueriesContext(connection) as captured:
            data = SupportAdminTicketDetailSerializer(prefetched).data

        assert data["ticket_number"] == ticket.ticket_number
        assert any(message["message_type"] == "internal_note" for message in data["messages"])
        assert len(captured) == 0

    def test_ticket_type_serializer_does_not_query_after_ticket_type_selector(self) -> None:
        SupportTicketTypeFactory(title="Nested Type A")
        SupportTicketTypeFactory(title="Nested Type B")
        ticket_types = list(selectors.get_active_ticket_types())

        with CaptureQueriesContext(connection) as captured:
            data = SupportTicketTypeSerializer(ticket_types, many=True).data

        assert len(data) >= 2
        assert len(captured) == 0


class TestSupportPermissionAndRouteContracts:
    """Final smoke tests for permissions and route contracts."""

    def test_anonymous_user_cannot_create_ticket(self) -> None:
        ticket_type = SupportTicketTypeFactory()

        response = APIClient().post(
            reverse("support_desk:user-ticket-list-create"),
            data={
                "ticket_type_id": ticket_type.pk,
                "subject": "مشکل ورود",
                "description": "امکان ورود به سایت را ندارم",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_regular_user_cannot_access_admin_analytics_or_exports(self) -> None:
        user = UserFactory()

        analytics = _client_for(user).get(reverse("support_desk:admin-analytics"))
        export = _client_for(user).get(reverse("support_desk:admin-export-tickets"))

        assert analytics.status_code == status.HTTP_403_FORBIDDEN
        assert export.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_route_contracts_are_registered(self) -> None:
        routes = [
            "admin-ticket-list",
            "admin-analytics",
            "admin-export-tickets",
            "admin-export-messages",
            "admin-export-sla",
            "admin-export-csat",
        ]

        for route in routes:
            assert reverse(f"support_desk:{route}")

    def test_closed_ticket_remains_visible_to_owner_history(self) -> None:
        ticket = _make_submitted_ticket()
        ticket.status = TicketStatus.CLOSED
        ticket.save(update_fields=["status", "updated_at"])

        response = _client_for(ticket.owner).get(
            reverse(
                "support_desk:user-ticket-detail", kwargs={"ticket_number": ticket.ticket_number}
            )
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["status"] == TicketStatus.CLOSED
