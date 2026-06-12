"""Managers for notification models."""

from django.db import models

from apps.notifications.choices import NotificationDeliveryStatus, NotificationEventStatus


class NotificationEventQuerySet(models.QuerySet):
    """Query helpers for notification events."""

    def pending(self):
        """Return pending events."""
        return self.filter(status=NotificationEventStatus.PENDING)


class NotificationDeliveryQuerySet(models.QuerySet):
    """Query helpers for deliveries."""

    def unread(self):
        """Return unread in-app deliveries."""
        return self.exclude(status=NotificationDeliveryStatus.READ)
