"""
Abstract base models shared across project applications.
"""

from django.db import models

from .managers import ActiveManager, AllObjectsManager


class BaseModel(models.Model):
    """BaseModel implementation for the core application."""
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="تاریخ بروزرسانی",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
    )

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def soft_delete(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def restore(self):
        self.is_active = True
        self.save(update_fields=["is_active", "updated_at"])


class CacheInvalidationEvent(BaseModel):
    """Durable outbox event for public cache/frontend revalidation."""

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
    )

    domain = models.CharField(max_length=80, db_index=True)
    tags = models.JSONField(default=list, blank=True)
    paths = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at", "created_at"], name="core_cache_event_due_idx"),
            models.Index(fields=["domain", "-created_at"], name="core_cache_event_domain_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.domain}:{self.status}:{self.pk}"
