"""Support C4 smart reply suggestion tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.support_desk.choices import KnowledgeArticleStatus, TicketMessageType, TicketStatus
from apps.support_desk.models import SupportKnowledgeArticleUse, SupportTicketMessage
from apps.support_desk.services import (
    create_canned_response,
    create_knowledge_article,
    generate_smart_reply_suggestions,
)
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.support_desk import (
    SupportCategoryFactory,
    SupportDepartmentFactory,
    SupportTicketFactory,
    SupportTicketMessageFactory,
    SupportTicketTypeFactory,
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


def _ticket_with_taxonomy(*, status_value=TicketStatus.SUBMITTED):
    """Create support ticket with consistent taxonomy."""
    department = SupportDepartmentFactory()
    category = SupportCategoryFactory(department=department)
    ticket_type = SupportTicketTypeFactory(default_department=department, default_category=category)
    ticket = SupportTicketFactory(
        owner=UserFactory(),
        department=department,
        category=category,
        ticket_type=ticket_type,
        status=status_value,
        subject="مشکل پرداخت و رسید",
        description_snapshot="برای پرداخت و دریافت رسید تراکنش مشکل دارم",
    )
    return ticket, department, category, ticket_type


def test_smart_reply_suggestions_use_kb_and_exclude_internal_notes() -> None:
    """Smart replies should be KB-backed and never include internal note content."""
    ticket, department, category, ticket_type = _ticket_with_taxonomy()
    internal_marker = "INTERNAL-NOTE-ONLY-MARKER"
    SupportTicketMessageFactory(
        ticket=ticket, author=ticket.owner, body="پرداخت من خطا دارد", is_internal=False
    )
    SupportTicketMessage.objects.create(
        ticket=ticket,
        author=AdminUserFactory(),
        message_type=TicketMessageType.INTERNAL_NOTE,
        body=internal_marker,
        is_internal=True,
        is_from_staff=True,
    )
    article = create_knowledge_article(
        title="راهنمای پرداخت و رسید",
        summary="حل مشکل پرداخت و دریافت رسید",
        body="مراحل پیگیری پرداخت و رسید را بررسی کنید.",
        department=department,
        category=category,
        ticket_type=ticket_type,
        keywords=["پرداخت", "رسید"],
        status=KnowledgeArticleStatus.PUBLISHED,
    )

    bundle = generate_smart_reply_suggestions(ticket=ticket)

    assert bundle.policy_version == "support-smart-replies/v1"
    assert bundle.suggestions[0].source_type == "knowledge_article"
    assert bundle.suggestions[0].source_id == article.pk
    assert internal_marker not in str([suggestion.body for suggestion in bundle.suggestions])
    assert "internal_notes_excluded" in bundle.safety_notes


def test_smart_reply_suggestions_include_canned_response_and_fallback() -> None:
    """Smart replies should combine canned responses and safe fallback."""
    ticket, department, category, _ticket_type = _ticket_with_taxonomy()
    canned = create_canned_response(
        title="پاسخ پرداخت",
        body="سلام، لطفاً شماره تراکنش پرداخت را ارسال کنید.",
        department=department,
        category=category,
    )

    bundle = generate_smart_reply_suggestions(ticket=ticket)

    source_pairs = {
        (suggestion.source_type, suggestion.source_id) for suggestion in bundle.suggestions
    }
    assert ("canned_response", canned.pk) in source_pairs
    assert any(suggestion.source_type == "fallback" for suggestion in bundle.suggestions)


def test_smart_reply_endpoint_audits_generation() -> None:
    """Admin smart reply endpoint should audit suggestion generation."""
    admin = AdminUserFactory()
    ticket, department, category, ticket_type = _ticket_with_taxonomy()
    create_knowledge_article(
        title="راهنمای رسید",
        body="رسید پرداخت از بخش مشارکت‌ها قابل مشاهده است.",
        department=department,
        category=category,
        ticket_type=ticket_type,
        keywords=["رسید", "پرداخت"],
        status=KnowledgeArticleStatus.PUBLISHED,
    )
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.get(
            reverse(
                "support_desk:admin-ticket-smart-replies",
                kwargs={"ticket_number": ticket.ticket_number},
            )
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["ticket_number"] == ticket.ticket_number
    assert response.data["data"]["suggestions"]
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.SUPPORT_SMART_REPLY_SUGGESTED in called_actions


def test_smart_reply_use_sends_reply_records_kb_use_and_audit() -> None:
    """Using reviewed smart reply should send admin reply, record KB use and audit."""
    admin = AdminUserFactory()
    ticket, department, category, ticket_type = _ticket_with_taxonomy(
        status_value=TicketStatus.WAITING_FOR_ADMIN
    )
    article = create_knowledge_article(
        title="راهنمای پرداخت",
        body="برای بررسی پرداخت شماره تراکنش را ارسال کنید.",
        department=department,
        category=category,
        ticket_type=ticket_type,
        keywords=["پرداخت"],
        status=KnowledgeArticleStatus.PUBLISHED,
    )
    client = _admin_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse(
                "support_desk:admin-ticket-smart-reply-use",
                kwargs={"ticket_number": ticket.ticket_number},
            ),
            data={
                "body": "سلام، برای بررسی پرداخت لطفاً شماره تراکنش را ارسال کنید.",
                "source_type": "knowledge_article",
                "source_id": article.pk,
            },
            format="json",
        )

    assert response.status_code == status.HTTP_201_CREATED
    assert SupportTicketMessage.objects.filter(
        ticket=ticket, is_from_staff=True, body__icontains="شماره تراکنش"
    ).exists()
    assert SupportKnowledgeArticleUse.objects.filter(
        article=article, ticket=ticket, used_by=admin, context="smart_reply"
    ).exists()
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.SUPPORT_SMART_REPLY_USED in called_actions
    assert audit_actions.SUPPORT_TICKET_REPLIED in called_actions
