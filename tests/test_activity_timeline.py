"""Apex B3 user activity timeline tests."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.activity.choices import ActivityVerb
from apps.activity.models import UserActivity
from apps.activity.services import infer_app_label, record_activity
from apps.notifications.choices import NotificationChannel
from apps.notifications.services import create_notification_event, dispatch_event
from tests.factories import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_record_activity_and_infer_app_label() -> None:
    """Activity service should infer app labels and persist timeline records."""
    user = UserFactory()
    actor = AdminUserFactory()

    activity = record_activity(
        user=user,
        actor=actor,
        event_type="support.reply",
        title="پاسخ پشتیبانی",
        summary="پیام جدید",
        aggregate_type="support_ticket",
        aggregate_id="SUP-1",
    )

    assert activity.app_label == "support_desk"
    assert activity.verb == ActivityVerb.REPLIED
    assert infer_app_label("kindness.high_match") == "kindness_wall"


def test_notification_event_creates_activity_timeline_entry() -> None:
    """Notification events should automatically create user activity entries."""
    user = UserFactory()

    event = create_notification_event(
        event_type="lms.certificate_issued",
        recipients=[user],
        channels=[NotificationChannel.IN_APP],
        payload={"title": "مدرک صادر شد", "course_title": "پایتون"},
        aggregate_type="lms_certificate",
        aggregate_id="42",
    )
    dispatch_event(event=event)

    activity = UserActivity.objects.get(user=user, event_type="lms.certificate_issued")
    assert activity.title == "مدرک صادر شد"
    assert activity.app_label == "lms"
    assert activity.aggregate_id == "42"


def test_user_activity_timeline_api_is_owner_scoped_and_filterable() -> None:
    """Users should only see their own timeline, with app filters."""
    user = UserFactory()
    other = UserFactory()
    record_activity(
        user=user, event_type="madadkar.payment_success", title="پرداخت موفق", app_label="madadkar"
    )
    record_activity(user=other, event_type="support.reply", title="پاسخ", app_label="support_desk")

    response = _client_for(user).get(
        reverse("activity:user-timeline"), data={"app_label": "madadkar"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["data"]["count"] == 1
    assert response.data["data"]["results"][0]["title"] == "پرداخت موفق"


def test_admin_activity_timeline_requires_admin() -> None:
    """Admin timeline must be protected."""
    user = UserFactory()
    record_activity(user=user, event_type="support.reply", title="پاسخ")

    denied = _client_for(user).get(reverse("activity:admin-timeline"))
    allowed = _client_for(AdminUserFactory()).get(reverse("activity:admin-timeline"))

    assert denied.status_code == status.HTTP_403_FORBIDDEN
    assert allowed.status_code == status.HTTP_200_OK
    assert allowed.data["data"]["count"] >= 1
