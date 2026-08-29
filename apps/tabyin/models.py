"""
Database models for synced Tabyin content and attachments.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel
from apps.tabyin.choices import ContentOrigin, MediaType, MirrorStatus, SubmissionStatus
from apps.tabyin.managers import (
    TabyinContentAllManager,
    TabyinContentManager,
)


class TabyinContent(BaseModel):
    """
    محتوای کرول‌شده از سایت محتوانگار.

    هر رکورد نمایانگر یک محتوا (پست/عکس/ویدئو) در بخش جهاد تبیین است.
    داده‌ها از منبع خارجی sync می‌شوند و در دیتابیس ما ذخیره می‌شوند.
    """

    # --- شناسه پایدار ---
    external_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="شناسه پایدار",
        help_text="برای محتوای خارجی id منبع و برای محتوای کاربر local UUID است.",
    )
    origin = models.CharField(
        max_length=20,
        choices=ContentOrigin.choices,
        default=ContentOrigin.EXTERNAL,
        db_index=True,
        verbose_name="منشأ محتوا",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tabyin_submissions",
        verbose_name="ارسال‌کننده",
    )
    submission_status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.APPROVED,
        db_index=True,
        verbose_name="وضعیت بررسی",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tabyin_reviewed_submissions",
        verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان بررسی",
    )
    admin_note = models.TextField(
        blank=True,
        default="",
        verbose_name="یادداشت ادمین",
    )

    # --- محتوای اصلی ---
    title = models.CharField(
        max_length=512,
        blank=True,
        default="",
        verbose_name="عنوان",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="توضیحات",
    )

    # --- اطلاعات منبع ---
    author_username = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="نام پدیدآورنده",
        help_text="مقدار username از محتوانگار.",
    )
    source_entity_id = models.PositiveIntegerField(
        default=0,
        verbose_name="entity_id منبع",
    )
    source_status = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="وضعیت در منبع",
    )
    source_type = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="نوع در منبع",
    )
    source_created_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاریخ ایجاد در منبع",
    )
    source_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاریخ ویرایش در منبع",
        db_index=True,
    )
    source_url = models.URLField(
        max_length=512,
        blank=True,
        default="",
        verbose_name="لینک محتوا در محتوانگار",
    )

    # --- همگام‌سازی ---
    raw_payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="داده خام JSON",
        help_text="کل JSON دریافتی از منبع برای دیباگ و بازیابی.",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="هش محتوا",
        help_text="SHA-256 فیلدهای کلیدی برای تشخیص تغییر.",
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="آخرین همگام‌سازی",
    )
    is_deleted_in_source = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="حذف‌شده در منبع",
    )

    # --- Managers ---
    objects = TabyinContentManager()
    all_objects = TabyinContentAllManager()

    class Meta:
        ordering = ["-source_created_at"]
        verbose_name = "محتوای تبیین"
        verbose_name_plural = "محتواهای تبیین"
        indexes = [
            models.Index(
                fields=[
                    "is_active",
                    "is_deleted_in_source",
                    "submission_status",
                    "-source_created_at",
                ],
                name="idx_tabyin_public_list",
            ),
            models.Index(
                fields=["origin", "submission_status", "-created_at"],
                name="idx_tabyin_submission_queue",
            ),
            models.Index(
                fields=["submitted_by", "submission_status", "-created_at"],
                name="idx_tabyin_user_submissions",
            ),
            models.Index(
                fields=["external_id"],
                name="idx_tabyin_external_id",
            ),
            models.Index(
                fields=["-last_synced_at"],
                name="idx_tabyin_last_synced",
            ),
        ]

    def __str__(self) -> str:
        return self.title or self.external_id

    def save(self, *args: object, **kwargs: object) -> None:
        """Generate local stable id and timestamps for user submissions."""
        if not self.external_id:
            self.external_id = f"local-{uuid.uuid4().hex}"
        if self.origin == ContentOrigin.USER_SUBMITTED and self.source_created_at is None:
            self.source_created_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def primary_media_type(self) -> str:
        """نوع رسانه اولین پیوست (برای فیلتر سریع در UI)."""
        first_attachment = self.attachments.first()
        if first_attachment:
            return first_attachment.media_type
        return MediaType.OTHER


class TabyinAttachment(BaseModel):
    """
    فایل پیوست یک محتوای تبیین.

    هر محتوا می‌تواند چندین پیوست (عکس، ویدئو) داشته باشد.
    """

    content = models.ForeignKey(
        TabyinContent,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="محتوا",
    )
    url = models.URLField(
        max_length=1024,
        verbose_name="آدرس کامل فایل",
    )
    relative_url = models.CharField(
        max_length=1024,
        blank=True,
        default="",
        verbose_name="آدرس نسبی فایل",
        help_text="مقدار خام url از JSON منبع.",
    )
    media_type = models.CharField(
        max_length=10,
        choices=MediaType.choices,
        default=MediaType.OTHER,
        db_index=True,
        verbose_name="نوع رسانه",
    )
    size = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="ابعاد",
        help_text="مثلاً 1280X905",
    )
    duration = models.PositiveIntegerField(
        default=0,
        verbose_name="مدت (ثانیه)",
        help_text="فقط برای ویدئو/صوت.",
    )
    file_size = models.PositiveIntegerField(
        default=0,
        verbose_name="حجم فایل (KB)",
    )
    title = models.CharField(
        max_length=512,
        blank=True,
        default="",
        verbose_name="عنوان فایل",
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="ترتیب",
    )

    # --- آینه‌سازی روی استوریج خودمان (پیوست‌های روایت‌های مردمی) ---
    origin_url = models.URLField(
        max_length=1024,
        blank=True,
        default="",
        verbose_name="نشانی اصلی پیش از آینه‌سازی",
        help_text="برای پیوست‌هایی که اول با نشانی بیرونی ثبت و بعد روی سرور ما ذخیره شدند.",
    )
    mirror_status = models.CharField(
        max_length=10,
        choices=MirrorStatus.choices,
        default=MirrorStatus.NONE,
        db_index=True,
        verbose_name="وضعیت آینه‌سازی",
    )
    mime_type = models.CharField(
        max_length=127,
        blank=True,
        default="",
        verbose_name="نوع MIME فایل",
    )

    class Meta:
        ordering = ["order"]
        verbose_name = "پیوست تبیین"
        verbose_name_plural = "پیوست‌های تبیین"

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} — {self.content.title[:30]}"


class TabyinUserSubmission(TabyinContent):
    """Proxy model exposing user-submitted Tabyin content as a dedicated admin queue."""

    class Meta:
        proxy = True
        verbose_name = "ارسال کاربر تبیین"
        verbose_name_plural = "ارسال‌های کاربران تبیین"
