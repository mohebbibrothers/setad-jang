"""Delivery providers for notification channels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings

from apps.authentication.providers import get_sms_otp_provider
from apps.core.mailing import send_text_email
from apps.notifications.choices import NotificationChannel


@dataclass(frozen=True)
class NotificationDeliveryResult:
    """Provider delivery result."""

    success: bool
    provider: str
    external_id: str = ""
    error_message: str = ""
    extra: dict[str, Any] | None = None


class NotificationProvider(Protocol):
    """Protocol for notification providers."""

    provider_name: str

    def send(
        self, *, recipient: str, subject: str, body: str, payload: dict[str, Any]
    ) -> NotificationDeliveryResult:
        """Send notification payload."""


class InAppNotificationProvider:
    """Provider representing already persisted in-app notifications."""

    provider_name = "in_app"

    def send(
        self, *, recipient: str, subject: str, body: str, payload: dict[str, Any]
    ) -> NotificationDeliveryResult:
        """In-app delivery is represented by the delivery row itself."""
        return NotificationDeliveryResult(success=True, provider=self.provider_name)


class EmailNotificationProvider:
    """Email notification provider backed by Django email backend."""

    provider_name = "django_email"

    def send(
        self, *, recipient: str, subject: str, body: str, payload: dict[str, Any]
    ) -> NotificationDeliveryResult:
        """Send an email notification."""
        try:
            send_text_email(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
            )
        except Exception as exc:
            return NotificationDeliveryResult(
                success=False, provider=self.provider_name, error_message=type(exc).__name__
            )
        return NotificationDeliveryResult(success=True, provider=self.provider_name)


class SMSNotificationProvider:
    """SMS notification provider using the configured OTP SMS adapter contract."""

    provider_name = "sms"

    def send(
        self, *, recipient: str, subject: str, body: str, payload: dict[str, Any]
    ) -> NotificationDeliveryResult:
        """Send an SMS notification through configured SMS adapter."""
        try:
            provider = get_sms_otp_provider()
            provider.send(recipient=recipient, code=body[:120], purpose="notification")
        except Exception as exc:
            return NotificationDeliveryResult(
                success=False, provider=self.provider_name, error_message=type(exc).__name__
            )
        return NotificationDeliveryResult(success=True, provider=self.provider_name)


class WebhookNotificationProvider:
    """Placeholder-safe webhook provider contract."""

    provider_name = "webhook_noop"

    def send(
        self, *, recipient: str, subject: str, body: str, payload: dict[str, Any]
    ) -> NotificationDeliveryResult:
        """Skip webhooks until a concrete endpoint registry is configured."""
        return NotificationDeliveryResult(
            success=False,
            provider=self.provider_name,
            error_message="webhook_provider_not_configured",
        )


def get_notification_provider(channel: str) -> NotificationProvider:
    """Return provider for a notification channel."""
    if channel == NotificationChannel.IN_APP:
        return InAppNotificationProvider()
    if channel == NotificationChannel.EMAIL:
        return EmailNotificationProvider()
    if channel == NotificationChannel.SMS:
        return SMSNotificationProvider()
    if channel == NotificationChannel.WEBHOOK:
        return WebhookNotificationProvider()
    raise ValueError(f"Unsupported notification channel: {channel}")
