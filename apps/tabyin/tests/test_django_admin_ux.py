"""Django admin UX tests for Tabyin.

Tabyin keeps a normalized content/attachment model, but admin UX is organized
around two real workspaces:
- TabyinContentAdmin for content visibility and sync operations.
- TabyinUserSubmissionAdmin for service-backed review of user submissions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib import admin
from django.urls import reverse

from apps.tabyin.admin import TabyinAttachmentInline
from apps.tabyin.choices import ContentOrigin, SubmissionStatus
from apps.tabyin.models import TabyinAttachment, TabyinContent, TabyinUserSubmission
from tests.factories import (
    AdminUserFactory,
    TabyinAttachmentFactory,
    TabyinContentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

_TASK_PATCH_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _user_submission(**kwargs) -> TabyinContent:
    user = kwargs.pop("submitted_by", None) or UserFactory(email="tabyin-submitter@test.local")
    return TabyinContentFactory(
        origin=ContentOrigin.USER_SUBMITTED,
        submitted_by=user,
        submission_status=SubmissionStatus.PENDING_REVIEW,
        is_active=False,
        **kwargs,
    )


class TestTabyinDjangoAdminUX:
    """Admin index and workspaces should match the product workflow."""

    def test_attachment_admin_is_hidden_but_content_and_submission_workspaces_are_visible(self, rf):
        request = rf.get("/admin/")
        request.user = AdminUserFactory()

        assert admin.site._registry[TabyinAttachment].get_model_perms(request) == {}
        assert admin.site._registry[TabyinContent].get_model_perms(request)
        assert admin.site._registry[TabyinUserSubmission].get_model_perms(request)

    def test_admin_index_hides_attachments_and_shows_user_submission_queue(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)

        response = client.get(reverse("admin:index"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "پیوست‌های تبیین" not in html
        assert "محتواهای تبیین" in html
        assert "ارسال‌های کاربران تبیین" in html

    def test_content_and_submission_admins_embed_attachment_inline(self):
        assert admin.site._registry[TabyinContent].inlines == [TabyinAttachmentInline]
        assert admin.site._registry[TabyinUserSubmission].inlines == [TabyinAttachmentInline]

    def test_submission_review_panel_is_rendered_for_pending_submission(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        submission = _user_submission(title="ارسال کاربر برای بررسی")
        TabyinAttachmentFactory(content=submission)

        response = client.get(reverse("admin:tabyin_tabyinusersubmission_change", args=[submission.pk]))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert "تأیید و انتشار" in html
        assert "رد ارسال" in html
        assert "tabyin_admin_note" in html

    def test_submission_admin_approve_uses_service_and_publishes_content(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        submission = _user_submission(title="محتوای قابل تأیید")

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                reverse("admin:tabyin_tabyinusersubmission_change", args=[submission.pk]),
                data={
                    "_tabyin_approve_submission": "1",
                    "tabyin_admin_note": "محتوا مناسب است.",
                },
                follow=True,
            )

        assert response.status_code == 200
        submission.refresh_from_db()
        assert submission.submission_status == SubmissionStatus.APPROVED
        assert submission.is_active is True
        assert submission.reviewed_by_id == admin_user.pk
        assert submission.admin_note == "محتوا مناسب است."
        mock_task.delay.assert_called_once()

    def test_submission_admin_reject_uses_service_and_keeps_content_hidden(self, client):
        admin_user = AdminUserFactory()
        client.force_login(admin_user)
        submission = _user_submission(title="محتوای نامناسب")

        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = client.post(
                reverse("admin:tabyin_tabyinusersubmission_change", args=[submission.pk]),
                data={
                    "_tabyin_reject_submission": "1",
                    "tabyin_admin_note": "نیازمند اصلاح است.",
                },
                follow=True,
            )

        assert response.status_code == 200
        submission.refresh_from_db()
        assert submission.submission_status == SubmissionStatus.REJECTED
        assert submission.is_active is False
        assert submission.reviewed_by_id == admin_user.pk
        assert submission.admin_note == "نیازمند اصلاح است."
        mock_task.delay.assert_called_once()

    def test_content_admin_sync_action_dispatches_through_service(self, rf, monkeypatch):
        request = rf.post("/admin/tabyin/tabyincontent/", HTTP_X_REQUEST_ID="admin-sync-req")
        request.user = AdminUserFactory()
        captured: dict[str, object] = {}
        messages: list[str] = []

        def fake_dispatch_sync_task(**kwargs):
            captured.update(kwargs)
            return "tabyin-admin-sync-task-id"

        monkeypatch.setattr("apps.tabyin.admin.services.dispatch_sync_task", fake_dispatch_sync_task)
        monkeypatch.setattr("apps.tabyin.admin.messages.success", lambda request, message: messages.append(message))
        with patch(_TASK_PATCH_PATH) as mock_task:
            mock_task.delay = MagicMock()
            admin.site._registry[TabyinContent].dispatch_incremental_sync(request, TabyinContent.objects.none())

        assert captured["mode"] == "incremental"
        assert captured["triggered_by_user_id"] == request.user.pk
        assert captured["request_id"] == "admin-sync-req"
        assert captured["dispatch_ip"] is not None
        assert "tabyin-admin-sync-task-id" in messages[0]
        mock_task.delay.assert_called_once()
