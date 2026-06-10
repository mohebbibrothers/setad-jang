"""
Database models for public report subjects, reports, and attachments.
"""

from django.db import models
from django.utils.text import slugify

from apps.core.models import BaseModel

from .choices import ReportStatus
from .validators import validate_image_extension, validate_image_size


def report_attachment_upload_path(instance, filename):
    """report_attachment_upload_path helper for the public_reports application."""
    return f"public_reports/{instance.report_id}/{filename}"


class ReportSubject(BaseModel):
    """ReportSubject implementation for the public_reports application."""
    title = models.CharField(max_length=150, unique=True, verbose_name="عنوان موضوع")
    slug = models.SlugField(max_length=170, unique=True, blank=True, verbose_name="شناسه")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")

    class Meta:
        verbose_name = "موضوع گزارش"
        verbose_name_plural = "موضوعات گزارش"
        ordering = ["order", "title"]
        indexes = [
            models.Index(fields=["is_active", "order", "title"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)
        super().save(*args, **kwargs)


class Report(BaseModel):
    """Report implementation for the public_reports application."""
    full_name = models.CharField(max_length=150, verbose_name="نام گزارش‌دهنده")
    phone_number = models.CharField(max_length=14, blank=True, null=True, verbose_name="شماره تماس")
    subject = models.ForeignKey(
        ReportSubject,
        on_delete=models.PROTECT,
        related_name="reports",
        verbose_name="موضوع گزارش",
    )
    description = models.TextField(verbose_name="توضیحات گزارش")

    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        verbose_name="وضعیت بررسی",
    )
    admin_note = models.TextField(blank=True, verbose_name="یادداشت ادمین")

    submitter_ip = models.GenericIPAddressField(
        blank=True, null=True, verbose_name="آی‌پی گزارش‌دهنده"
    )

    class Meta:
        verbose_name = "گزارش مردمی"
        verbose_name_plural = "گزارشات مردمی"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["subject", "status", "-created_at"]),
            models.Index(fields=["submitter_ip", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.full_name} - {self.subject.title}"


class ReportAttachment(BaseModel):
    """ReportAttachment implementation for the public_reports application."""
    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="گزارش",
    )
    image = models.ImageField(
        upload_to=report_attachment_upload_path,
        validators=[validate_image_extension, validate_image_size],
        verbose_name="تصویر مستند",
    )

    class Meta:
        verbose_name = "تصویر مستند"
        verbose_name_plural = "تصاویر مستندات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Attachment for Report #{self.report_id}"
