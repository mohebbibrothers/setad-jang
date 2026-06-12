"""Database models for cross-app user activity timeline."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.activity.choices import ActivityVerb, ActivityVisibility
from apps.core.models import BaseModel


class UserActivity(BaseModel):
    """A normalized timeline event for a user across all project apps."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_actions")
    event_type = models.CharField(max_length=160, db_index=True)
    app_label = models.CharField(max_length=80, db_index=True)
    verb = models.CharField(max_length=40, choices=ActivityVerb.choices, default=ActivityVerb.NOTIFIED)
    title = models.CharField(max_length=260)
    summary = models.TextField(blank=True)
    aggregate_type = models.CharField(max_length=120, blank=True)
    aggregate_id = models.CharField(max_length=120, blank=True)
    visibility = models.CharField(max_length=20, choices=ActivityVisibility.choices, default=ActivityVisibility.PRIVATE)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "رویداد فعالیت کاربر"
        verbose_name_plural = "رویدادهای فعالیت کاربران"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
            models.Index(fields=["app_label", "-created_at"]),
            models.Index(fields=["aggregate_type", "aggregate_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.event_type}:{self.title}"
