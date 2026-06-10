"""
Managers اپ مددکار.

این managerها روی BaseModel.ActiveManager سوار می‌شوند و queryهای پرتکرار
(مثل حرکت‌های قابل نمایش عمومی) را در یک نقطه centralize می‌کنند.

نکته معماری:
- ActiveManager از apps.core.managers فقط is_active=True را برمی‌گرداند.
- managerهای اختصاصی اینجا فیلترهای بیزنسی اضافه می‌کنند.
- برای دسترسی به همه رکوردها (حتی soft-deleted) از `all_objects` استفاده شود.
"""

from __future__ import annotations

from django.db import models

from apps.core.managers import ActiveManager


class CampaignVisibleManager(ActiveManager):
    """
    Manager حرکت‌های قابل نمایش عمومی.

    شرایط نمایش:
    - is_active=True (از ActiveManager به ارث می‌رسد)
    - is_visible=True (ادمین کنترل می‌کند)
    - status در [PUBLISHED, COMPLETED, CLOSED]

    حرکت‌های DRAFT هرگز در API عمومی نمایش داده نمی‌شوند.
    """

    def get_queryset(self) -> models.QuerySet:
        from apps.madadkar.choices import CampaignStatus

        return (
            super()
            .get_queryset()
            .filter(
                is_visible=True,
                status__in=[
                    CampaignStatus.PUBLISHED,
                    CampaignStatus.COMPLETED,
                    CampaignStatus.CLOSED,
                ],
            )
        )


class CampaignAcceptingSharesManager(ActiveManager):
    """
    Manager حرکت‌هایی که فعلاً سهم می‌پذیرند.

    شرایط:
    - is_active=True
    - is_visible=True
    - status=PUBLISHED
    - purchased_shares < total_shares
    - deadline منقضی نشده (در صورت has_deadline)

    این manager برای validation سریع در serializer مشارکت استفاده می‌شود.
    فیلتر deadline در سطح Python چک نمی‌شود — برای دقت بیشتر در service انجام شود.
    """

    def get_queryset(self) -> models.QuerySet:
        from apps.madadkar.choices import CampaignStatus

        return (
            super()
            .get_queryset()
            .filter(
                is_visible=True,
                status=CampaignStatus.PUBLISHED,
            )
        )
