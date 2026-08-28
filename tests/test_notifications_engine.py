"""Apex A2 notification engine tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.notifications.choices import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEventStatus,
)
from apps.notifications.models import (
    NotificationPreference,
    NotificationTemplate,
)
from apps.notifications.services import (
    NotificationServiceError,
    create_notification_event,
    dispatch_event,
    mark_all_read,
    mark_delivery_read,
    render_notification,
    set_preference,
)
from apps.notifications.tasks import dispatch_notification_event_task
from tests.factories import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestNotificationServiceContracts:
    """Notification service and provider contracts."""

    def test_create_event_renders_templates_and_respects_preferences(self) -> None:
        user = UserFactory(email="notify@example.com")
        muted = UserFactory(email="muted@example.com")
        NotificationTemplate.objects.update_or_create(
            code="support.reply",
            channel=NotificationChannel.IN_APP,
            defaults={
                "title": "پاسخ پشتیبانی",
                "subject_template": "تیکت {ticket_number}",
                "body_template": "پاسخ جدید برای {ticket_number}: {message}",
            },
        )
        set_preference(
            user=muted,
            event_type="support.reply",
            channel=NotificationChannel.IN_APP,
            enabled=False,
        )

        event = create_notification_event(
            event_type="support.reply",
            recipients=[user, muted],
            channels=[NotificationChannel.IN_APP],
            payload={"ticket_number": "SUP-1", "message": "سلام"},
            aggregate_type="support_ticket",
            aggregate_id="SUP-1",
        )

        assert event.deliveries.count() == 1
        delivery = event.deliveries.get()
        assert delivery.recipient == user
        assert delivery.subject == "تیکت SUP-1"
        assert "سلام" in delivery.body

    def test_dispatch_event_marks_delivery_and_event_status(self) -> None:
        user = UserFactory()
        event = create_notification_event(
            event_type="generic.event",
            recipients=[user],
            channels=[NotificationChannel.IN_APP],
            payload={"title": "عنوان", "message": "متن"},
        )

        dispatch_event(event=event)
        event.refresh_from_db()
        delivery = event.deliveries.get()

        assert event.status == NotificationEventStatus.SENT
        assert delivery.status == NotificationDeliveryStatus.SENT
        assert delivery.provider == "in_app"
        assert delivery.sent_at is not None

    def test_email_provider_failure_sets_failed_delivery_and_event_failed(self) -> None:
        user = UserFactory(email="broken@example.com")
        event = create_notification_event(
            event_type="email.event",
            recipients=[user],
            channels=[NotificationChannel.EMAIL],
            payload={"title": "Email", "message": "Body"},
        )

        with patch("apps.notifications.providers.send_mail", side_effect=RuntimeError("smtp down")):
            dispatch_event(event=event)

        event.refresh_from_db()
        delivery = event.deliveries.get()
        assert event.status == NotificationEventStatus.FAILED
        assert delivery.status == NotificationDeliveryStatus.FAILED
        assert delivery.error_message == "RuntimeError"

    def test_mark_read_and_mark_all_read_are_owner_safe(self) -> None:
        user = UserFactory()
        other = UserFactory()
        event = create_notification_event(event_type="x", recipients=[user], payload={"title": "x"})
        dispatch_event(event=event)
        delivery = event.deliveries.get()

        with pytest.raises(NotificationServiceError):
            mark_delivery_read(delivery=delivery, user=other)

        mark_delivery_read(delivery=delivery, user=user)
        delivery.refresh_from_db()
        assert delivery.status == NotificationDeliveryStatus.READ

        event2 = create_notification_event(
            event_type="x", recipients=[user], payload={"title": "x"}
        )
        dispatch_event(event=event2)
        assert mark_all_read(user=user) >= 1

    def test_render_notification_fallback_is_safe_for_missing_template_vars(self) -> None:
        NotificationTemplate.objects.update_or_create(
            code="missing.var",
            channel=NotificationChannel.IN_APP,
            defaults={
                "title": "Missing",
                "subject_template": "سلام {name}",
                "body_template": "کد {missing}",
            },
        )

        subject, body = render_notification(
            event_type="missing.var", channel=NotificationChannel.IN_APP, payload={"name": "علی"}
        )

        assert subject == "سلام علی"
        assert body == "کد {missing}"

    def test_dispatch_task_processes_event(self) -> None:
        event = create_notification_event(
            event_type="task.event", recipients=[UserFactory()], payload={"title": "Task"}
        )

        result = dispatch_notification_event_task(event.pk)

        assert result == NotificationEventStatus.SENT


class TestNotificationAPIs:
    """Notification inbox/admin API tests."""

    def test_user_inbox_mark_read_preferences_and_admin_lists(self) -> None:
        user = UserFactory()
        admin = AdminUserFactory()
        event = create_notification_event(
            event_type="api.event", recipients=[user], payload={"title": "اعلان", "message": "متن"}
        )
        dispatch_event(event=event)
        delivery = event.deliveries.get()
        client = _client_for(user)

        inbox = client.get(reverse("notifications:inbox"))
        assert inbox.status_code == status.HTTP_200_OK
        assert inbox.data["data"]["count"] == 1

        read = client.post(reverse("notifications:mark-read", kwargs={"delivery_id": delivery.pk}))
        assert read.status_code == status.HTTP_200_OK
        assert read.data["data"]["status"] == NotificationDeliveryStatus.READ

        preference = client.post(
            reverse("notifications:preferences"),
            data={
                "event_type": "api.event",
                "channel": NotificationChannel.EMAIL,
                "enabled": False,
            },
            format="json",
        )
        assert preference.status_code == status.HTTP_201_CREATED
        assert NotificationPreference.objects.filter(
            user=user, event_type="api.event", channel=NotificationChannel.EMAIL, enabled=False
        ).exists()

        assert (
            _client_for(admin).get(reverse("notifications:admin-event-list")).status_code
            == status.HTTP_200_OK
        )
        assert (
            _client_for(admin).get(reverse("notifications:admin-delivery-list")).status_code
            == status.HTTP_200_OK
        )
        assert (
            _client_for(admin).get(reverse("notifications:admin-template-list")).status_code
            == status.HTTP_200_OK
        )

    def test_regular_user_cannot_access_admin_notification_lists(self) -> None:
        user = UserFactory()

        response = _client_for(user).get(reverse("notifications:admin-event-list"))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_mark_all_read_endpoint(self) -> None:
        user = UserFactory()
        event = create_notification_event(
            event_type="bulk", recipients=[user], payload={"title": "Bulk"}
        )
        dispatch_event(event=event)

        response = _client_for(user).post(reverse("notifications:mark-all-read"))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["updated"] >= 1
