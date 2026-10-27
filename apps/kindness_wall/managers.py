"""QuerySet/Managerهای تختهٔ دیوار مهربانی."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from apps.kindness_wall.choices import ListingStatus

if TYPE_CHECKING:  # pragma: no cover - فقط برای type-checker (اجتناب از circular import)
    from apps.kindness_wall.models import KindnessListing  # noqa: F401 — مصرف در subscript رشته‌ای


class KindnessListingQuerySet(models.QuerySet["KindnessListing"]):
    """سلوک‌های مشترک کوئری آگهی."""

    def board(self) -> KindnessListingQuerySet:
        """آگهی‌های جاریِ روی تختهٔ عمومی (منتشرشده و نامنقضی)."""
        now = timezone.now()
        return self.filter(is_active=True, status=ListingStatus.PUBLISHED).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )

    def published(self) -> KindnessListingQuerySet:
        """همان ``board`` — نام سازگار با بقیهٔ اپ‌های پروژه."""
        return self.board()

    def fulfilled(self) -> KindnessListingQuerySet:
        """بایگانیِ «داستان‌های مهربانی»."""
        return self.filter(is_active=True, status=ListingStatus.FULFILLED)

    def expiring_before(self, when) -> KindnessListingQuerySet:
        """جاری‌هایی که تا ``when`` منقضی می‌شوند (صف یادآوری ادمین)."""
        return self.filter(is_active=True, status=ListingStatus.PUBLISHED, expires_at__lte=when)


class KindnessListingManager(models.Manager.from_queryset(KindnessListingQuerySet)):
    """منیجر پیش‌فرض؛ ردیف‌های سافت‌حذف‌شده را نشان نمی‌دهد."""

    def get_queryset(self) -> KindnessListingQuerySet:
        """فیلتر خودکار is_active."""
        return super().get_queryset().filter(is_active=True)
