"""
Database models for synced Tabyin content and attachments.
"""

from django.db import models

from apps.core.models import BaseModel
from apps.tabyin.choices import MediaType
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

    # --- شناسه منبع ---
    external_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="شناسه منبع",
        help_text="شناسه یکتای محتوا در سایت محتوانگار (مقدار id در JSON).",
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
                fields=["is_active", "is_deleted_in_source", "-source_created_at"],
                name="idx_tabyin_public_list",
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

    class Meta:
        ordering = ["order"]
        verbose_name = "پیوست تبیین"
        verbose_name_plural = "پیوست‌های تبیین"

    def __str__(self) -> str:
        return f"{self.get_media_type_display()} — {self.content.title[:30]}"
