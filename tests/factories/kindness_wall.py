"""Factories برای تست‌های دیوار مهربانی (v2 — تختهٔ نیاز ادمین‌محور).

سیاست جدید، آگهی را ادمین می‌سازد؛ پس کارخانه‌ها هم ادمین‌محورند:
کاربرِ آگهی (owner) و تگ و تطبیق حذف، در مقابل کانال‌های تماس واقعیِ
پرشدنی و انتشارِ آمادهٔ نمایش روی تخته اضافه شده است.
"""

from __future__ import annotations

from datetime import timedelta

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.kindness_wall.choices import ListingStatus, Urgency
from apps.kindness_wall.models import KindnessCategory, KindnessListing


class KindnessCategoryFactory(DjangoModelFactory):
    """دستهٔ فعال؛ slug از عنوان و به دست خودِ model ساخته می‌شود (تستِ مسیر واقعی)."""

    class Meta:
        model = KindnessCategory

    title = factory.Sequence(lambda n: f"دسته مهربانی {n}")
    description = "توضیحات دسته"
    order = factory.Sequence(lambda n: n)
    is_active = True


class KindnessListingFactory(DjangoModelFactory):
    """آگهی آمادهٔ انتشار با یک راه تماس معتبر (پیش‌فرض: پیش‌نویس امن).

    پیش‌فرض روی ``draft`` است تا هر تستی که انتظار دیدنِ آگهی روی تخته را
    دارد صریحاً از PublishedNeedListingFactory یا status=PUBLISHED استفاده کند
    — خوانا و ضدتصادف؛ انتشار هم قاعدهٔ «حداقل یک راه تماس» را پاس می‌کند.
    """

    class Meta:
        model = KindnessListing

    category = factory.SubFactory(KindnessCategoryFactory)
    title = factory.Sequence(lambda n: f"آگهی مهربانی {n}")
    description = "توضیح کامل آگهی برای کمک‌رسانی و ارتباط انسانی با صاحب نیاز"
    quantity = 1
    unit = "عدد"
    urgency = Urgency.NORMAL
    status = ListingStatus.DRAFT
    province = "تهران"
    city = "تهران"
    contact_phone = "09121234567"
    is_active = True


class PublishedNeedListingFactory(KindnessListingFactory):
    """آگهی جاری روی تخته (منتشرشده، با انقضای آینده و یک کانال تماس).

    ستون فقرات تست‌های عمومی/جستجو: هر کوئری‌ستِ «تخته» باید این ردیف را
    ببیند و تست‌های انقضا روی همین ردیفِ backdate شده اجرا می‌شوند.
    """

    status = ListingStatus.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=30))


__all__ = [
    "KindnessCategoryFactory",
    "KindnessListingFactory",
    "PublishedNeedListingFactory",
]
