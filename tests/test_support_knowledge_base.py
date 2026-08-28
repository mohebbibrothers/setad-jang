"""Support C3 knowledge base integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit_logs import actions as audit_actions
from apps.support_desk.choices import KnowledgeArticleStatus
from apps.support_desk.models import SupportKnowledgeArticleUse
from apps.support_desk.services import (
    create_knowledge_article,
    publish_knowledge_article,
    recommend_knowledge_articles,
)
from tests.factories.auth import AdminUserFactory, UserFactory
from tests.factories.support_desk import (
    SupportCategoryFactory,
    SupportDepartmentFactory,
    SupportTicketFactory,
    SupportTicketTypeFactory,
)

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _jwt_client(user) -> APIClient:
    """Build JWT-authenticated client."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token!s}")
    return client


def test_knowledge_article_recommendation_uses_keywords_and_taxonomy() -> None:
    """Recommendation service should combine keyword overlap and taxonomy boosts."""
    department = SupportDepartmentFactory()
    category = SupportCategoryFactory(department=department)
    ticket_type = SupportTicketTypeFactory(default_department=department, default_category=category)
    article = create_knowledge_article(
        title="راهنمای مشکل پرداخت",
        summary="رفع خطای پرداخت و رسید",
        body="برای پیگیری تراکنش و رسید پرداخت این راهنما را بخوانید.",
        department=department,
        category=category,
        ticket_type=ticket_type,
        keywords=["پرداخت", "رسید", "تراکنش"],
        status=KnowledgeArticleStatus.PUBLISHED,
    )
    create_knowledge_article(
        title="راهنمای حساب کاربری",
        body="ورود و رمز عبور",
        keywords=["ورود"],
        status=KnowledgeArticleStatus.PUBLISHED,
    )

    recommendations = recommend_knowledge_articles(
        text="برای پرداخت و دریافت رسید مشکل دارم",
        department=department,
        category=category,
        ticket_type=ticket_type,
    )

    assert recommendations[0] == article


def test_public_knowledge_article_list_detail_and_recommend_endpoint() -> None:
    """Authenticated users should browse and receive public knowledge recommendations."""
    user = UserFactory()
    department = SupportDepartmentFactory()
    article = publish_knowledge_article(
        article=create_knowledge_article(
            title="آپلود مدارک در تیکت",
            summary="راهنمای آپلود فایل",
            body="برای آپلود مدرک، از بخش ضمیمه‌ها استفاده کنید.",
            department=department,
            keywords=["آپلود", "مدرک"],
        ),
    )
    create_knowledge_article(title="پیش‌نویس محرمانه", body="نباید عمومی باشد")
    client = _jwt_client(user)

    list_response = client.get(
        reverse("support_desk:knowledge-article-list"), data={"search": "آپلود"}
    )
    detail_response = client.get(
        reverse("support_desk:knowledge-article-detail", kwargs={"slug": article.slug})
    )
    recommend_response = client.post(
        reverse("support_desk:knowledge-article-recommend"),
        data={
            "subject": "مشکل آپلود",
            "description": "آپلود مدرک انجام نمی‌شود",
            "department_id": department.pk,
        },
        format="json",
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data["data"]["count"] == 1
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.data["data"]["slug"] == article.slug
    assert recommend_response.status_code == status.HTTP_200_OK
    assert recommend_response.data["data"][0]["id"] == article.pk


def test_admin_knowledge_article_lifecycle_and_audit() -> None:
    """Admin should create/update/publish/archive articles with audit actions."""
    admin = AdminUserFactory()
    department = SupportDepartmentFactory()
    client = _jwt_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        create_response = client.post(
            reverse("support_desk:admin-knowledge-article-list-create"),
            data={
                "title": "راهنمای SLA",
                "summary": "توضیح SLA",
                "body": "متن کامل راهنما",
                "department_id": department.pk,
                "keywords": ["sla", "زمان پاسخ"],
            },
            format="json",
        )
        article_id = create_response.data["data"]["id"]
        update_response = client.patch(
            reverse(
                "support_desk:admin-knowledge-article-detail", kwargs={"article_id": article_id}
            ),
            data={"summary": "توضیح به‌روز SLA"},
            format="json",
        )
        publish_response = client.post(
            reverse(
                "support_desk:admin-knowledge-article-publish", kwargs={"article_id": article_id}
            )
        )
        archive_response = client.post(
            reverse(
                "support_desk:admin-knowledge-article-archive", kwargs={"article_id": article_id}
            )
        )

    assert create_response.status_code == status.HTTP_201_CREATED
    assert update_response.status_code == status.HTTP_200_OK
    assert publish_response.status_code == status.HTTP_200_OK
    assert archive_response.status_code == status.HTTP_200_OK
    assert archive_response.data["data"]["status"] == KnowledgeArticleStatus.ARCHIVED
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.SUPPORT_KB_ARTICLE_CREATED in called_actions
    assert audit_actions.SUPPORT_KB_ARTICLE_UPDATED in called_actions
    assert audit_actions.SUPPORT_KB_ARTICLE_PUBLISHED in called_actions
    assert audit_actions.SUPPORT_KB_ARTICLE_ARCHIVED in called_actions


def test_admin_article_use_records_usage_and_audit() -> None:
    """Using an article in support context should increment usage and create usage event."""
    admin = AdminUserFactory()
    article = publish_knowledge_article(
        article=create_knowledge_article(title="راهنمای پاسخ", body="متن پاسخ")
    )
    ticket = SupportTicketFactory(status="submitted")
    client = _jwt_client(admin)

    with patch(_AUDIT_TASK_PATH) as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            reverse("support_desk:admin-knowledge-article-use", kwargs={"article_id": article.pk}),
            data={"ticket_number": ticket.ticket_number, "context": "reply"},
            format="json",
        )

    assert response.status_code == status.HTTP_201_CREATED
    article.refresh_from_db()
    assert article.usage_count == 1
    assert SupportKnowledgeArticleUse.objects.filter(
        article=article, ticket=ticket, used_by=admin
    ).exists()
    called_actions = [call.kwargs.get("action") for call in mock_task.delay.call_args_list]
    assert audit_actions.SUPPORT_KB_ARTICLE_USED in called_actions
