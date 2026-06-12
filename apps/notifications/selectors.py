"""Read-side selectors for notifications."""

from django.db.models import QuerySet

from apps.notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
    NotificationTemplate,
)


def get_user_deliveries(*, user_id: int) -> QuerySet[NotificationDelivery]:
    """Return notifications for a user."""
    return NotificationDelivery.objects.filter(recipient_id=user_id).select_related("event").order_by("-created_at")


def get_user_unread_deliveries(*, user_id: int) -> QuerySet[NotificationDelivery]:
    """Return unread in-app notifications for a user."""
    return get_user_deliveries(user_id=user_id).unread()


def get_user_delivery_by_id(*, user_id: int, delivery_id: int) -> NotificationDelivery | None:
    """Return one delivery with owner protection."""
    return get_user_deliveries(user_id=user_id).filter(pk=delivery_id).first()


def get_admin_events() -> QuerySet[NotificationEvent]:
    """Return notification events for admin inspection."""
    return NotificationEvent.objects.select_related("actor").prefetch_related("deliveries").order_by("-created_at")


def get_admin_deliveries() -> QuerySet[NotificationDelivery]:
    """Return notification deliveries for admin inspection."""
    return NotificationDelivery.objects.select_related("event", "recipient").order_by("-created_at")


def get_admin_templates() -> QuerySet[NotificationTemplate]:
    """Return notification templates for admin management."""
    return NotificationTemplate.objects.order_by("code", "channel")


def get_user_preferences(*, user_id: int) -> QuerySet[NotificationPreference]:
    """Return notification preferences for a user."""
    return NotificationPreference.objects.filter(user_id=user_id).order_by("event_type", "channel")
