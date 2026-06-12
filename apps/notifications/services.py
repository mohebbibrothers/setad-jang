"""Service layer for notification events, deliveries and preferences."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.notifications.choices import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEventStatus,
    NotificationPriority,
)
from apps.notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
    NotificationTemplate,
    render_template_string,
)
from apps.notifications.providers import get_notification_provider


class NotificationServiceError(Exception):
    """Base notification service exception."""


@transaction.atomic
def create_notification_event(
    *,
    event_type: str,
    recipients: Iterable[Any],
    channels: Iterable[str] = (NotificationChannel.IN_APP,),
    payload: dict[str, Any] | None = None,
    actor: Any | None = None,
    aggregate_type: str = "",
    aggregate_id: str = "",
    priority: str = NotificationPriority.NORMAL,
) -> NotificationEvent:
    """Create event and pending deliveries for enabled recipient preferences."""
    payload = payload or {}
    event = NotificationEvent.objects.create(
        event_type=event_type,
        actor=actor if getattr(actor, "pk", None) else None,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        priority=priority,
    )
    for recipient in recipients:
        for channel in channels:
            if _preference_enabled(user=recipient, event_type=event_type, channel=channel):
                subject, body = render_notification(event_type=event_type, channel=channel, payload=payload)
                NotificationDelivery.objects.get_or_create(
                    event=event,
                    recipient=recipient,
                    channel=channel,
                    defaults={"subject": subject, "body": body},
                )
    return event


def render_notification(*, event_type: str, channel: str, payload: dict[str, Any]) -> tuple[str, str]:
    """Render notification subject/body from template or safe fallback."""
    template = NotificationTemplate.objects.filter(code=event_type, channel=channel, is_active=True).first()
    if template:
        return (
            render_template_string(template.subject_template, payload),
            render_template_string(template.body_template, payload),
        )
    title = str(payload.get("title") or event_type)
    body = str(payload.get("message") or title)
    return title, body


@transaction.atomic
def dispatch_event(*, event: NotificationEvent) -> NotificationEvent:
    """Dispatch all pending deliveries for a notification event."""
    event.status = NotificationEventStatus.PROCESSING
    event.attempt_count += 1
    event.save(update_fields=["status", "attempt_count", "updated_at"])
    sent = failed = 0
    for delivery in event.deliveries.filter(status=NotificationDeliveryStatus.PENDING):
        result = get_notification_provider(delivery.channel).send(
            recipient=_recipient_address(delivery),
            subject=delivery.subject,
            body=delivery.body,
            payload=event.payload,
        )
        delivery.provider = result.provider
        delivery.external_id = result.external_id
        if result.success:
            delivery.status = NotificationDeliveryStatus.SENT
            delivery.sent_at = timezone.now()
            sent += 1
        else:
            delivery.status = NotificationDeliveryStatus.FAILED
            delivery.error_message = result.error_message
            failed += 1
        delivery.save(update_fields=["provider", "external_id", "status", "sent_at", "error_message", "updated_at"])
    event.status = NotificationEventStatus.SENT if failed == 0 else (NotificationEventStatus.PARTIAL if sent else NotificationEventStatus.FAILED)
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "processed_at", "updated_at"])
    return event


@transaction.atomic
def mark_delivery_read(*, delivery: NotificationDelivery, user: Any) -> NotificationDelivery:
    """Mark a user-owned delivery as read."""
    if delivery.recipient_id != user.pk:
        raise NotificationServiceError("این اعلان متعلق به کاربر جاری نیست.")
    delivery.status = NotificationDeliveryStatus.READ
    delivery.read_at = timezone.now()
    delivery.save(update_fields=["status", "read_at", "updated_at"])
    return delivery


@transaction.atomic
def mark_all_read(*, user: Any) -> int:
    """Mark all current user's deliveries as read."""
    now = timezone.now()
    updated = NotificationDelivery.objects.filter(recipient=user).exclude(status=NotificationDeliveryStatus.READ).update(status=NotificationDeliveryStatus.READ, read_at=now, updated_at=now)
    return int(updated)


@transaction.atomic
def set_preference(*, user: Any, event_type: str, channel: str, enabled: bool) -> NotificationPreference:
    """Set a user's preference for an event/channel pair."""
    preference, _created = NotificationPreference.objects.update_or_create(
        user=user,
        event_type=event_type,
        channel=channel,
        defaults={"enabled": enabled},
    )
    return preference


def _preference_enabled(*, user: Any, event_type: str, channel: str) -> bool:
    """Return whether a user allows the event/channel delivery."""
    preference = NotificationPreference.objects.filter(user=user, event_type=event_type, channel=channel).first()
    return True if preference is None else preference.enabled


def _recipient_address(delivery: NotificationDelivery) -> str:
    """Return recipient address based on delivery channel."""
    user = delivery.recipient
    if delivery.channel == NotificationChannel.EMAIL:
        return getattr(user, "email", "") or ""
    if delivery.channel == NotificationChannel.SMS:
        return getattr(user, "phone_number", "") or ""
    if delivery.channel == NotificationChannel.WEBHOOK:
        return str(delivery.event.payload.get("webhook_url", ""))
    return str(user.pk)
