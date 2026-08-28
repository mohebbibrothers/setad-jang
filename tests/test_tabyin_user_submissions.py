"""
Tabyin user submission workflow tests.

این تست‌ها قابلیت جدید بانک محتوای تبیین را پوشش می‌دهند:
- کاربران احرازشده می‌توانند محتوا ارسال کنند.
- محتوای کاربر ابتدا pending است و public نمی‌شود.
- ادمین می‌تواند approve/reject کند.
- فقط approved روی public list/detail نمایش داده می‌شود.
- owner-based IDOR و audit dispatch رعایت می‌شود.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.tabyin.choices import ContentOrigin, MediaType, SubmissionStatus
from apps.tabyin.models import TabyinContent
from apps.tabyin.services import SubmissionNotReviewable, approve_user_submission
from tests.factories.auth import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Build an authenticated APIClient for a user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _submit_payload(title: str = "محتوای مردمی") -> dict:
    """Payload استاندارد ارسال محتوای کاربر."""
    return {
        "title": title,
        "description": "توضیح کامل محتوای پیشنهادی توسط کاربر",
        "attachments": [
            {
                "url": "https://example.com/media/image-1.png",
                "media_type": MediaType.IMAGE,
                "title": "تصویر اول",
                "order": 0,
            }
        ],
    }


class TestUserTabyinSubmissionFlow:
    """تست‌های جریان ارسال محتوا توسط کاربر."""

    def test_authenticated_user_can_submit_content_for_review(self) -> None:
        user = UserFactory(email="submitter@example.com")
        client = _client_for(user)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                reverse("tabyin:user-submission-list-create"),
                data=_submit_payload(),
                format="json",
            )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["success"] is True
        data = response.data["data"]
        assert data["submission_status"] == SubmissionStatus.PENDING_REVIEW
        assert len(data["attachments"]) == 1

        content = TabyinContent.all_objects.get(pk=data["id"])
        assert content.origin == ContentOrigin.USER_SUBMITTED
        assert content.submitted_by_id == user.pk
        assert content.is_active is False
        assert content.external_id.startswith("local-")

        mock_task.delay.assert_called_once()
        assert (
            mock_task.delay.call_args.kwargs["action"]
            == audit_actions.TABYIN_USER_SUBMISSION_SUBMITTED
        )

    def test_anonymous_user_cannot_submit_content(self) -> None:
        response = APIClient().post(
            reverse("tabyin:user-submission-list-create"),
            data=_submit_payload(),
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert TabyinContent.all_objects.count() == 0

    def test_pending_submission_is_not_visible_in_public_list(self) -> None:
        user = UserFactory()
        client = _client_for(user)
        client.post(
            reverse("tabyin:user-submission-list-create"),
            data=_submit_payload(title="پنهان تا تأیید"),
            format="json",
        )

        response = APIClient().get(reverse("tabyin:public-content-list"))

        assert response.status_code == status.HTTP_200_OK
        titles = [item["title"] for item in response.data["data"]["results"]]
        assert "پنهان تا تأیید" not in titles

    def test_user_can_only_retrieve_own_submission(self) -> None:
        owner = UserFactory(email="owner@example.com")
        other = UserFactory(email="other@example.com")
        create_response = _client_for(owner).post(
            reverse("tabyin:user-submission-list-create"),
            data=_submit_payload(),
            format="json",
        )
        content_id = create_response.data["data"]["id"]

        response = _client_for(other).get(
            reverse("tabyin:user-submission-detail", kwargs={"content_id": content_id})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestAdminTabyinSubmissionReview:
    """تست‌های بررسی محتوا توسط ادمین."""

    def test_admin_can_approve_submission_and_make_it_public(self) -> None:
        user = UserFactory()
        admin = AdminUserFactory(email="tabyin-admin@example.com")
        create_response = _client_for(user).post(
            reverse("tabyin:user-submission-list-create"),
            data=_submit_payload(title="قابل انتشار"),
            format="json",
        )
        content_id = create_response.data["data"]["id"]

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(admin).post(
                reverse("tabyin:admin-submission-approve", kwargs={"content_id": content_id}),
                data={"admin_note": "مورد تأیید است"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["submission_status"] == SubmissionStatus.APPROVED
        content = TabyinContent.all_objects.get(pk=content_id)
        assert content.is_active is True
        assert content.reviewed_by_id == admin.pk
        assert content.admin_note == "مورد تأیید است"

        public_detail = APIClient().get(
            reverse("tabyin:public-content-detail", kwargs={"external_id": content.external_id})
        )
        assert public_detail.status_code == status.HTTP_200_OK
        assert public_detail.data["data"]["title"] == "قابل انتشار"
        assert audit_actions.TABYIN_USER_SUBMISSION_APPROVED in [
            call.kwargs["action"] for call in mock_task.delay.call_args_list
        ]

    def test_admin_can_reject_submission_and_keep_it_private(self) -> None:
        user = UserFactory()
        admin = AdminUserFactory(email="tabyin-reviewer@example.com")
        create_response = _client_for(user).post(
            reverse("tabyin:user-submission-list-create"),
            data=_submit_payload(title="رد شده"),
            format="json",
        )
        content_id = create_response.data["data"]["id"]

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(admin).post(
                reverse("tabyin:admin-submission-reject", kwargs={"content_id": content_id}),
                data={"admin_note": "نیازمند اصلاح"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        content = TabyinContent.all_objects.get(pk=content_id)
        assert content.submission_status == SubmissionStatus.REJECTED
        assert content.is_active is False
        assert content.admin_note == "نیازمند اصلاح"

        public_detail = APIClient().get(
            reverse("tabyin:public-content-detail", kwargs={"external_id": content.external_id})
        )
        assert public_detail.status_code == status.HTTP_404_NOT_FOUND
        assert audit_actions.TABYIN_USER_SUBMISSION_REJECTED in [
            call.kwargs["action"] for call in mock_task.delay.call_args_list
        ]

    def test_submission_cannot_be_reviewed_twice(self) -> None:
        user = UserFactory()
        admin = AdminUserFactory()
        create_response = _client_for(user).post(
            reverse("tabyin:user-submission-list-create"),
            data=_submit_payload(),
            format="json",
        )
        content = TabyinContent.all_objects.get(pk=create_response.data["data"]["id"])
        approve_user_submission(content=content, admin=admin)
        content.refresh_from_db()

        with pytest.raises(SubmissionNotReviewable):
            approve_user_submission(content=content, admin=admin)

    def test_admin_submission_queue_filters_by_status(self) -> None:
        user = UserFactory()
        admin = AdminUserFactory()
        for title in ["اول", "دوم"]:
            _client_for(user).post(
                reverse("tabyin:user-submission-list-create"),
                data=_submit_payload(title=title),
                format="json",
            )
        first = TabyinContent.all_objects.get(title="اول")
        approve_user_submission(content=first, admin=admin)

        response = _client_for(admin).get(
            reverse("tabyin:admin-submission-list"),
            data={"submission_status": SubmissionStatus.PENDING_REVIEW},
        )

        assert response.status_code == status.HTTP_200_OK
        titles = [item["title"] for item in response.data["data"]["results"]]
        assert titles == ["دوم"]
