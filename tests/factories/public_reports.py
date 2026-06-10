"""
Factories اپ گزارشات مردمی.

این ماژول factoryهای مرتبط با گزارشات و موضوعات را تعریف می‌کند:
- ReportSubjectFactory: ساخت یک موضوع گزارش فعال
- ReportFactory: ساخت یک گزارش مردمی با موضوع

اصول طراحی:
- مقادیر پیش‌فرض باید معنادار و یکتا باشند.
- روابط (FK) به‌صورت SubFactory مدیریت می‌شوند.
- هیچ business logic داخل factory نیست؛ فقط ساخت داده.
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from apps.public_reports.choices import ReportStatus
from apps.public_reports.models import Report, ReportSubject


class ReportSubjectFactory(DjangoModelFactory):
    """Factory برای ساخت یک موضوع گزارش فعال."""

    class Meta:
        model = ReportSubject
        django_get_or_create = ("title",)

    title = factory.Sequence(lambda n: f"موضوع تست {n}")
    description = factory.Faker("paragraph", nb_sentences=2, locale="fa_IR")
    order = factory.Sequence(lambda n: n)
    is_active = True


class ReportFactory(DjangoModelFactory):
    """Factory برای ساخت یک گزارش مردمی."""

    class Meta:
        model = Report

    full_name = factory.Faker("name", locale="fa_IR")
    phone_number = factory.Sequence(lambda n: f"0912{n:07d}")
    subject = factory.SubFactory(ReportSubjectFactory)
    description = factory.Faker("paragraph", nb_sentences=3, locale="fa_IR")
    status = ReportStatus.PENDING
    submitter_ip = "127.0.0.1"
