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
from django.db import IntegrityError, models, router, transaction

from apps.core.models import BaseModel

# ============================================================
# Chain constants
# ============================================================

#: previous_hash of the very first record in the chain.
GENESIS_HASH = "0" * 64

#: chain_index of the very first record. Positions are 1-based so that a
#: falsy value can never be mistaken for a valid position.
GENESIS_CHAIN_INDEX = 1

#: How many times an insert may re-read the chain head after losing a race.
#: Each retry costs one indexed single-row lookup, so this is cheap even at
#: the tail of a very hot chain.
CHAIN_INSERT_MAX_ATTEMPTS = 8


# ============================================================
# Exceptions
# ============================================================


class AuditLogImmutableError(PermissionError):
    """Raised when code attempts to mutate or delete an existing audit log."""


class AuditLogChainContentionError(RuntimeError):
    """Raised when an audit insert loses the chain-position race repeatedly."""


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
    request_id = models.CharField(
        max_length=80, null=True, blank=True, verbose_name="شناسه درخواست"
    )
    user_agent = models.CharField(max_length=512, blank=True, verbose_name="User-Agent")
    path = models.CharField(max_length=512, blank=True, verbose_name="مسیر درخواست")
    method = models.CharField(max_length=10, blank=True, verbose_name="متد HTTP")
    resource_type = models.CharField(max_length=100, verbose_name="نوع منبع")
    resource_id = models.CharField(max_length=100, null=True, blank=True, verbose_name="شناسه منبع")

    # برای ثبت تغییرات فیلدها به‌صورت JSON (مثلاً قبل: فعال، بعد: غیرفعال)
    changes = models.JSONField(null=True, blank=True, verbose_name="تغییرات")

    extra_data = models.JSONField(null=True, blank=True, verbose_name="داده اضافی")

    previous_hash = models.CharField(max_length=64, blank=True, verbose_name="هش قبلی")
    event_hash = models.CharField(max_length=64, blank=True, unique=True, verbose_name="هش رویداد")
    hash_version = models.PositiveSmallIntegerField(default=1, verbose_name="نسخه هش")

    # موقعیت قطعی رکورد در زنجیره.
    #
    # این ستون دو مسئله‌ی حیاتی را همزمان حل می‌کند:
    #
    # ۱. یکتایی آن در سطح دیتابیس، «انشعاب زنجیره» را از نظر ساختاری
    #    غیرممکن می‌کند. پیش‌تر دو insert همزمان می‌توانستند هر دو یک
    #    previous_hash را بخوانند و زنجیره را دو شاخه کنند؛ چون هر دو
    #    event_hash متفاوتی داشتند، constraint موجود جلوی آن را نمی‌گرفت
    #    و tamper-evidence بی‌صدا از بین می‌رفت.
    # ۲. ایندکس یکتای آن، پیدا کردن سر زنجیره را از یک sort روی کل جدول
    #    به یک index scan تک‌ردیفی تبدیل می‌کند.
    #
    # null=True فقط به‌عنوان escape hatch برای restore/replication سطح پایین
    # نگه داشته شده؛ مسیر اپلیکیشن همیشه آن را پر می‌کند.
    chain_index = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="موقعیت در زنجیره",
    )

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
            # ordering پیش‌فرض مدل روی -created_at است؛ بدون این ایندکس هر
            # لیست بدون فیلتری روی جدول audit به sort کامل تبدیل می‌شود.
            models.Index(fields=["-created_at"], name="audit_created_at_desc_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.user or 'Anonymous'} at {self.created_at}"

    @classmethod
    def _read_chain_head(cls, *, using: str) -> dict[str, Any] | None:
        """
        خواندن آخرین حلقه‌ی زنجیره با یک index scan تک‌ردیفی.

        فیلتر `chain_index__isnull=False` صرفاً دفاعی نیست: در PostgreSQL
        مرتب‌سازی نزولی به‌صورت پیش‌فرض NULLها را اول می‌آورد، پس بدون این
        فیلتر یک ردیف بدون chain_index می‌توانست به‌اشتباه سر زنجیره تلقی شود.
        """
        return (
            cls.all_objects.using(using)
            .filter(chain_index__isnull=False)
            .order_by("-chain_index")
            .values("chain_index", "event_hash")
            .first()
        )

    def _link_to_chain_head(self, *, using: str) -> None:
        """محاسبه‌ی chain_index/previous_hash/event_hash بر اساس سر فعلی زنجیره."""
        head = self._read_chain_head(using=using)
        if head is None:
            self.chain_index = GENESIS_CHAIN_INDEX
            self.previous_hash = GENESIS_HASH
        else:
            self.chain_index = int(head["chain_index"]) + 1
            self.previous_hash = head["event_hash"]
        self.event_hash = self.compute_event_hash(previous_hash=self.previous_hash)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """
        Allow initial insert but reject updates to preserve append-only records.

        استراتژی همزمانی: optimistic concurrency control.

        به‌جای گرفتن قفل (که در یک تراکنش کسب‌وکاری طولانی، تمام نوشتن‌های
        audit را سریال می‌کرد) رکورد را خوش‌بینانه با موقعیت بعدی زنجیره
        می‌نویسیم. اگر نویسنده‌ی دیگری همان موقعیت را گرفته باشد، constraint
        یکتای `chain_index` خطا می‌دهد و ما سر زنجیره را دوباره می‌خوانیم.

        این روش:
        - هیچ قفلی را در طول I/O یا تراکنش بیرونی نگه نمی‌دارد.
        - انشعاب زنجیره را از نظر ساختاری غیرممکن می‌کند، نه صرفاً بعید.
        - در حالت بدون رقابت دقیقاً یک SELECT سبک و یک INSERT هزینه دارد.
        - روی PostgreSQL و SQLite یکسان کار می‌کند.
        """
        if self.pk and not self._state.adding:
            raise AuditLogImmutableError("ویرایش لاگ‌های فعالیت مجاز نیست.")

        # رکورد از پیش مهرشده (restore/replication): همان‌طور که هست درج می‌شود.
        if self.chain_index is not None and self.previous_hash and self.event_hash:
            super().save(*args, **kwargs)
            return

        using = (
            kwargs.get("using") or self._state.db or router.db_for_write(type(self), instance=self)
        )
        last_error: Exception | None = None

        for _attempt in range(CHAIN_INSERT_MAX_ATTEMPTS):
            self._link_to_chain_head(using=using)
            try:
                # savepoint اختصاصی: اگر رقابت رخ دهد فقط همین insert برمی‌گردد
                # و تراکنش کسب‌وکاری بیرونی سالم می‌ماند.
                with transaction.atomic(using=using):
                    super().save(*args, **kwargs)
            except IntegrityError as exc:
                last_error = exc
                self.pk = None
                self._state.adding = True
                continue
            return

        raise AuditLogChainContentionError(
            "ثبت لاگ فعالیت به دلیل رقابت مداوم روی موقعیت زنجیره ممکن نشد.",
        ) from last_error

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
        encoded = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
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
