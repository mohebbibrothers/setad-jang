"""
Managers اپ R4J — Reward for Justice.

اصول طراحی:
- جداسازی scopeهای public / admin / active برای جلوگیری از تکرار فیلتر.
- soft-delete-aware: queryهای public هرگز رکوردهای غیرفعال را نمی‌بینند.
- published-aware: فقط ادمین می‌تواند draftها را ببیند.
- annotated managers: pre-computed annotations برای performance.
- ordering deterministic: تمام querysetهایی که برای pagination استفاده می‌شوند
  باید order صریح و پایدار داشته باشند تا UnorderedObjectListWarning رخ ندهد.

نکته مهم:
- در Django، استفاده از annotate ممکن است ordering پیش‌فرض مدل را
  از بین ببرد یا نامشخص کند.
- بنابراین managerهای paginated باید صراحتاً order_by داشته باشند.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Count, Q, Sum


class R4JCriminalActiveManager(models.Manager):
    """
    فقط رکوردهای فعال (is_active=True) را برمی‌گرداند.

    مناسب برای admin panel که draftها را هم نیاز دارد ببیند
    ولی soft-deleted نباید بیاید.

    Ordering:
    - صریح و deterministic برای سازگاری بهتر با pagination
    - created_at به‌عنوان sort اصلی
    - pk به‌عنوان tie-breaker
    """

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(is_active=True).order_by("-created_at", "-pk")


class R4JCriminalPublishedManager(models.Manager):
    """
    فقط رکوردهای فعال و منتشرشده — مخصوص نمایش به public.

    Annotations:
    - ``active_bounties_sum``: مجموع مبالغ bountyهای فعال
    - ``active_bounties_count``: تعداد bountyهای فعال

    از این annotations استفاده می‌شود تا از denormalized counters
    به‌عنوان fallback استفاده نشود و داده‌ی live هم در دسترس باشد.

    Ordering:
    - چون annotate روی queryset اعمال می‌شود، باید order صریح تنظیم شود
      تا paginator با queryset unordered مواجه نشود.
    - ترتیب پایدار:
        1) جدیدترین رکوردها اول
        2) در صورت برابری created_at، pk نزولی به‌عنوان tie-breaker
    """

    def get_queryset(self) -> models.QuerySet:
        from .choices import BountyStatus

        active_bounty_q = Q(
            bounties__status__in=[
                BountyStatus.ACTIVE,
                BountyStatus.CANCEL_REQUESTED,
            ],
            bounties__is_active=True,
        )

        return (
            super()
            .get_queryset()
            .filter(is_active=True, is_published=True)
            .annotate(
                active_bounties_sum=Sum(
                    "bounties__amount_toman",
                    filter=active_bounty_q,
                    default=0,
                ),
                active_bounties_count=Count(
                    "bounties",
                    filter=active_bounty_q,
                ),
            )
            .order_by("-created_at", "-pk")
        )
