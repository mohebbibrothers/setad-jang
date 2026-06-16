"""
Database models for append-only forensic activity audit logging.

Audit logs are security records, not business entities. They can be created, read
and indexed, but they must never be mutated or deleted through application code.
This module enforces that rule at model/manager level in addition to admin/API
read-only boundaries.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel

# ============================================================
# Exceptions
# ============================================================


class AuditLogImmutableError(PermissionError):
    """Raised when code attempts to mutate or delete an existing audit log."""


# ============================================================
# QuerySet / Manager
# ============================================================


class AuditLogQuerySet(models.QuerySet):
    """QuerySet that blocks bulk mutations for audit-log immutability."""

    def update(self, **kwargs: Any) -> int:
        """Block bulk updates because audit logs are append-only."""
        raise AuditLogImmutableError("ویرایش لاگ‌های فعالیت مجاز نیست.")

    def delete(self) -> tuple[int, dict[str, int]]:
        """Block bulk deletes because audit logs are append-only."""
        raise AuditLogImmutableError("حذف لاگ‌های فعالیت مجاز نیست.")

    def soft_delete(self) -> None:
        """Block inherited soft-delete style operations."""
        raise AuditLogImmutableError("حذف لاگ‌های فعالیت مجاز نیست.")

    def restore(self) -> None:
        """Block restore operations because audit logs are never soft-deleted."""
        raise AuditLogImmutableError("بازیابی روی لاگ فعالیت معنا ندارد.")


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
    """Manager for append-only audit logs."""


# ============================================================
# Audit Log Model
# ============================================================


class AuditLog(BaseModel):
    """
    ثبت فعالیت‌های حساس و سیستمی.

    این مدل append-only است: فقط ایجاد و خواندن مجاز است. update/delete حتی در
    سطح model و bulk queryset هم مسدود شده تا audit trail قابل اتکا بماند.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="کاربر",
    )
    action = models.CharField(max_length=100, verbose_name="عملیات")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="آدرس IP")
    request_id = models.CharField(max_length=80, null=True, blank=True, verbose_name="شناسه درخواست")
    user_agent = models.CharField(max_length=512, blank=True, verbose_name="User-Agent")
    path = models.CharField(max_length=512, blank=True, verbose_name="مسیر درخواست")
    method = models.CharField(max_length=10, blank=True, verbose_name="متد HTTP")
    resource_type = models.CharField(max_length=100, verbose_name="نوع منبع")
    resource_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="شناسه منبع")

    # برای ثبت تغییرات فیلدها به‌صورت JSON (مثلاً قبل: فعال، بعد: غیرفعال)
    changes = models.JSONField(null=True, blank=True, verbose_name="تغییرات")

    extra_data = models.JSONField(null=True, blank=True, verbose_name="داده اضافی")

    previous_hash = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="هش قبلی")
    event_hash = models.CharField(max_length=64, blank=True, unique=True, db_index=True, verbose_name="هش رویداد")
    hash_version = models.PositiveSmallIntegerField(default=1, verbose_name="نسخه هش")

    objects = AuditLogManager()
    all_objects = AuditLogManager()

    class Meta:
        verbose_name = "لاگ فعالیت"
        verbose_name_plural = "لاگ‌های فعالیت"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["resource_type", "resource_id", "-created_at"]),
            models.Index(fields=["request_id"]),
            models.Index(fields=["ip_address", "-created_at"]),
            models.Index(fields=["method", "path"]),
            models.Index(fields=["previous_hash"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.user or 'Anonymous'} at {self.created_at}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Allow initial insert but reject updates to preserve append-only records."""
        if self.pk and not self._state.adding:
            raise AuditLogImmutableError("ویرایش لاگ‌های فعالیت مجاز نیست.")
        if not self.previous_hash:
            previous = AuditLog.all_objects.order_by("-created_at", "-id").first()
            self.previous_hash = previous.event_hash if previous else "0" * 64
        if not self.event_hash:
            self.event_hash = self.compute_event_hash(previous_hash=self.previous_hash)
        super().save(*args, **kwargs)

    def compute_event_hash(self, *, previous_hash: str | None = None) -> str:
        """Compute deterministic hash for tamper-evident audit chain."""
        payload = {
            "hash_version": self.hash_version,
            "previous_hash": previous_hash if previous_hash is not None else self.previous_hash,
            "user_id": self.user_id,
            "action": self.action,
            "ip_address": self.ip_address,
            "request_id": self.request_id,
            "user_agent": self.user_agent,
            "path": self.path,
            "method": self.method,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "changes": self.changes,
            "extra_data": self.extra_data,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Block hard delete on audit records."""
        raise AuditLogImmutableError("حذف لاگ‌های فعالیت مجاز نیست.")

    def soft_delete(self) -> None:
        """Block soft-delete inherited from BaseModel."""
        raise AuditLogImmutableError("حذف لاگ‌های فعالیت مجاز نیست.")

    def restore(self) -> None:
        """Block restore operations for append-only audit records."""
        raise AuditLogImmutableError("بازیابی روی لاگ فعالیت معنا ندارد.")
