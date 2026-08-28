"""Database models for cross-app notification engine."""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.notifications.choices import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEventStatus,
    NotificationPriority,
)
from apps.notifications.managers import NotificationDeliveryQuerySet, NotificationEventQuerySet


class NotificationTemplate(BaseModel):
    """Admin-managed template for notification rendering."""

    code = models.SlugField(max_length=120)
    title = models.CharField(max_length=180)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    subject_template = models.CharField(max_length=260, blank=True)
    body_template = models.TextField()
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["code", "channel"]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "channel"], name="uniq_notification_template_code_channel"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code}:{self.channel}"


class NotificationEvent(BaseModel):
    """A domain event that should produce one or more notification deliveries."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=160, db_index=True)
    aggregate_type = models.CharField(max_length=120, blank=True)
    aggregate_id = models.CharField(max_length=120, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_events_created",
    )
    payload = models.JSONField(default=dict, blank=True)
    priority = models.CharField(
        max_length=20, choices=NotificationPriority.choices, default=NotificationPriority.NORMAL
    )
    status = models.CharField(
        max_length=20,
        choices=NotificationEventStatus.choices,
        default=NotificationEventStatus.PENDING,
        db_index=True,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    objects = NotificationEventQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_retry_at", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.uuid}"


class NotificationDelivery(BaseModel):
    """Per-recipient, per-channel notification delivery row."""

    event = models.ForeignKey(
        NotificationEvent, on_delete=models.CASCADE, related_name="deliveries"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_deliveries"
    )
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    status = models.CharField(
        max_length=20,
        choices=NotificationDeliveryStatus.choices,
        default=NotificationDeliveryStatus.PENDING,
        db_index=True,
    )
    subject = models.CharField(max_length=260, blank=True)
    body = models.TextField()
    provider = models.CharField(max_length=80, blank=True)
    external_id = models.CharField(max_length=160, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    objects = NotificationDeliveryQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "channel", "status", "-created_at"]),
            models.Index(fields=["event", "channel"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "recipient", "channel"],
                name="uniq_notification_delivery_event_recipient_channel",
            )
        ]

    def __str__(self) -> str:
        return f"{self.recipient_id}:{self.channel}:{self.status}"


class NotificationPreference(BaseModel):
    """User notification preferences per event type/channel."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    event_type = models.CharField(max_length=160)
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "event_type", "channel"], name="uniq_notification_preference"
            )
        ]
        indexes = [models.Index(fields=["user", "event_type", "channel"])]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.event_type}:{self.channel}={self.enabled}"


def render_template_string(template: str, context: dict[str, Any]) -> str:
    """Render a minimal safe format template using Python format_map."""

    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return template.format_map(SafeDict(context or {}))
