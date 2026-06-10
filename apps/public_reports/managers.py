"""
Managers اپ گزارشات مردمی.

این ماژول aliasهای domain-specific روی managerهای عمومی core تعریف می‌کند تا
مدل‌های گزارشات مردمی naming واضح و قابل توسعه داشته باشند، بدون اینکه منطق
soft-delete/active filtering در چند جای پروژه تکرار شود.
"""

from apps.core.managers import ActiveManager, AllObjectsManager


class ReportManager(ActiveManager):
    """Manager پیش‌فرض برای query کردن فقط رکوردهای فعال گزارشات مردمی."""


class ReportAllManager(AllObjectsManager):
    """Manager مدیریتی برای دسترسی به همه رکوردها، شامل soft-deletedها."""
