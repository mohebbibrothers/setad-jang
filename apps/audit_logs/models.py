"""
Database models for append-only forensic activity audit logging.

Audit logs are security records, not business entities. They can be created, read
and indexed, but they must never be mutated or deleted through application code.
This module enforces that rule at model/manager level in addition to admin/API
read-only boundaries.
"""

from __future__ import annotations

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
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.user or 'Anonymous'} at {self.created_at}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Allow initial insert but reject updates to preserve append-only records."""
        if self.pk and not self._state.adding:
            raise AuditLogImmutableError("ویرایش لاگ‌های فعالیت مجاز نیست.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Block hard delete on audit records."""
        raise AuditLogImmutableError("حذف لاگ‌های فعالیت مجاز نیست.")

    def soft_delete(self) -> None:
        """Block soft-delete inherited from BaseModel."""
        raise AuditLogImmutableError("حذف لاگ‌های فعالیت مجاز نیست.")

    def restore(self) -> None:
        """Block restore operations for append-only audit records."""
        raise AuditLogImmutableError("بازیابی روی لاگ فعالیت معنا ندارد.")
