from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel

# ============================================================
# Audit Log Model
# ============================================================

class AuditLog(BaseModel):
    """
    ثبت فعالیت‌های حساس و سیستمی.
    این مدل فقط قابلیت ایجاد دارد و هرگز نباید تغییر یا حذف (حتی soft delete) شود.
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
    request_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="شناسه درخواست")
    resource_type = models.CharField(max_length=100, verbose_name="نوع منبع")
    resource_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="شناسه منبع")

    # برای ثبت تغییرات فیلدها به‌صورت JSON (مثلاً قبل: فعال، بعد: غیرفعال)
    changes = models.JSONField(null=True, blank=True, verbose_name="تغییرات")

    extra_data = models.JSONField(null=True, blank=True, verbose_name="داده اضافی")

    class Meta:
        verbose_name = "لاگ فعالیت"
        verbose_name_plural = "لاگ‌های فعالیت"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action"]),
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["request_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.user or 'Anonymous'} at {self.created_at}"

    # صریحاً متدهای BaseModel را برای جلوگیری از حذف یا ویرایش غیرفعال می‌کنیم
    def soft_delete(self) -> None:
        raise PermissionError("حذف لاگ‌های فعالیت مجاز نیست.")

    def restore(self) -> None:
        raise PermissionError("بازیابی روی لاگ فعالیت معنا ندارد.")
