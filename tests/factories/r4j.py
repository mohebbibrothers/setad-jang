"""
Factories اپ R4J — Reward for Justice.

این ماژول factoryهای مورد نیاز تست‌های R4J را تعریف می‌کند:

- R4JCriminalFactory          : ساخت پروفایل مجرم (draft)
- R4JCriminalPublishedFactory : ساخت پروفایل مجرم منتشرشده
- R4JReportFactory            : ساخت گزارش community با status پیش‌فرض PENDING
- R4JReportFieldChangeFactory : ساخت یک پیشنهاد تغییر فیلد برای report
- R4JReportAttachmentFactory  : ساخت ضمیمه برای report
- R4JBountyFactory            : ساخت bounty فعال برای یک کاربر و مجرم

اصول طراحی:
- مقادیر یکتا و قابل پیش‌بینی برای جلوگیری از flaky tests.
- روابط از طریق SubFactory ساخته می‌شوند.
- فایل‌های واقعی به‌صورت in-memory ساخته می‌شوند.
- R4JCriminalPublishedFactory برای تست‌هایی که به criminal منتشرشده نیاز دارند
  بدون فراخوانی publish() service استفاده می‌شود.
- R4JBountyFactory مستقیماً روی DB کار می‌کند و counter sync را bypass می‌کند؛
  در تست‌هایی که counter sync را تست می‌کنند باید از service layer استفاده شود.
"""

from __future__ import annotations

import factory
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.r4j.choices import (
    BountyStatus,
    CriminalAttachmentKind,
    Gender,
    ReportFieldChangeStatus,
    ReportStatus,
)
from apps.r4j.models import (
    R4JBounty,
    R4JCriminal,
    R4JReport,
    R4JReportAttachment,
    R4JReportFieldChange,
)
from tests.factories.auth import UserFactory


class R4JCriminalFactory(DjangoModelFactory):
    """
    Factory برای ساخت یک پروفایل مجرم — به‌صورت پیش‌فرض draft.

    برای ساخت criminal منتشرشده از R4JCriminalPublishedFactory استفاده کن.
    """

    class Meta:
        model = R4JCriminal

    first_name = factory.Sequence(lambda n: f"FirstName{n}")
    last_name = factory.Sequence(lambda n: f"LastName{n}")
    gender = Gender.UNKNOWN
    country = "ایران"
    province = "تهران"
    city = "تهران"
    description = factory.Faker("paragraph", nb_sentences=2, locale="en_US")
    is_published = False
    is_active = True
    total_bounty_toman = 0
    bounties_count = 0


class R4JCriminalPublishedFactory(R4JCriminalFactory):
    """
    Factory برای ساخت یک پروفایل مجرم منتشرشده.

    از این factory در تست‌هایی که نیاز به criminal public دارند
    استفاده کن تا نیازی به فراخوانی publish() نباشد.
    """

    is_published = True
    published_at = factory.LazyFunction(timezone.now)


class R4JReportFactory(DjangoModelFactory):
    """
    Factory برای ساخت گزارش community.

    پیش‌فرض: status=PENDING، بدون field_change.
    برای افزودن field_change از R4JReportFieldChangeFactory استفاده کن.
    """

    class Meta:
        model = R4JReport

    criminal = factory.SubFactory(R4JCriminalFactory)
    submitted_by = factory.SubFactory(UserFactory)
    notes = factory.Faker("paragraph", nb_sentences=1, locale="en_US")
    status = ReportStatus.PENDING


class R4JReportFieldChangeFactory(DjangoModelFactory):
    """
    Factory برای ساخت یک پیشنهاد تغییر فیلد.

    پیش‌فرض: field_name="first_name"، status=PENDING.
    """

    class Meta:
        model = R4JReportFieldChange

    report = factory.SubFactory(R4JReportFactory)
    field_name = "first_name"
    suggested_value = factory.Sequence(lambda n: f"SuggestedValue{n}")
    current_value_snapshot = factory.Sequence(lambda n: f"OldValue{n}")
    status = ReportFieldChangeStatus.PENDING
    admin_note = ""


class R4JReportAttachmentFactory(DjangoModelFactory):
    """Factory برای ساخت ضمیمه گزارش — فایل minimal in-memory."""

    class Meta:
        model = R4JReportAttachment

    report = factory.SubFactory(R4JReportFactory)
    title = factory.Sequence(lambda n: f"attachment-{n}")
    kind = CriminalAttachmentKind.DOCUMENT

    @factory.lazy_attribute
    def file(self) -> SimpleUploadedFile:
        """ساخت یک فایل minimal in-memory برای تست."""
        return SimpleUploadedFile(
            f"test_attachment_{self.title}.pdf",
            b"%PDF-1.4 minimal content",
            content_type="application/pdf",
        )


class R4JBountyFactory(DjangoModelFactory):
    """
    Factory برای ساخت bounty فعال.

    نکات مهم:
    - این factory مستقیماً روی DB کار می‌کند و _sync_criminal_bounty_counters
      را فراخوانی نمی‌کند.
    - در تست‌هایی که رفتار counter sync را verify می‌کنند، باید از
      services.set_or_update_bounty() استفاده شود نه این factory.
    - برای ساخت bounty با status خاص، پارامتر status را override کن.

    Example:
        # bounty فعال
        bounty = R4JBountyFactory(criminal=criminal, user=user)

        # bounty در حال درخواست لغو
        bounty = R4JBountyFactory(
            criminal=criminal,
            user=user,
            status=BountyStatus.CANCEL_REQUESTED,
        )
    """

    class Meta:
        model = R4JBounty

    criminal = factory.SubFactory(R4JCriminalFactory)
    user = factory.SubFactory(UserFactory)
    amount_toman = 100_000
    status = BountyStatus.ACTIVE
    admin_note = ""
