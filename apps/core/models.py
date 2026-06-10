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
