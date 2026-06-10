"""
Factory-boy factories اپ مددکار.

این factoryها برای تست‌نویسی استفاده می‌شوند و یک مسیر سریع و تمیز
برای ساخت نمونه‌های معتبر از مدل‌ها فراهم می‌کنند.

نکات طراحی:
- مقادیر پیش‌فرض همگی valid هستند (پاس می‌کنن از constraints).
- traitها برای ساخت سریع نمونه‌های مخصوص (PublishedCampaignFactory).
- SubFactory برای ساخت خودکار وابستگی‌ها.
- تصاویر تست با Pillow ساخته می‌شوند تا هم برای FileField و هم برای
  ImageField (که Pillow-validation انجام می‌دهد) معتبر باشند.
"""

from __future__ import annotations

import io

import factory
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.madadkar.choices import (
    CampaignStatus,
    ParticipationStatus,
    PaymentStatus,
)
from apps.madadkar.models import (
    Campaign,
    CampaignImage,
    Participation,
    Payment,
    Sponsor,
)
from tests.factories.auth import UserFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_valid_png_bytes(width: int = 10, height: int = 10) -> bytes:
    """
    ساخت یک PNG معتبر برای تست با Pillow.

    این bytes هم برای FileField معتبر است و هم Pillow-validation داخلی
    DRF ImageField را پاس می‌کند.
    """
    buffer = io.BytesIO()
    image = Image.new("RGB", (width, height), color=(255, 0, 0))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _make_image_file(name: str = "test.png") -> SimpleUploadedFile:
    """ساخت یک فایل تصویر معتبر in-memory برای تست upload."""
    return SimpleUploadedFile(
        name=name,
        content=_generate_valid_png_bytes(),
        content_type="image/png",
    )


# ---------------------------------------------------------------------------
# SponsorFactory
# ---------------------------------------------------------------------------

class SponsorFactory(factory.django.DjangoModelFactory):
    """Factory پایه برای Sponsor — بدون لوگو."""

    class Meta:
        model = Sponsor
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"مددکار تستی {n}")


class SponsorWithLogoFactory(SponsorFactory):
    """Sponsor همراه با لوگو."""

    logo = factory.LazyFunction(lambda: _make_image_file("sponsor_logo.png"))


# ---------------------------------------------------------------------------
# CampaignFactory
# ---------------------------------------------------------------------------

class CampaignFactory(factory.django.DjangoModelFactory):
    """
    Factory پایه برای Campaign در وضعیت DRAFT.

    مقادیر پیش‌فرض:
    - total_amount = 10,000,000,000 تومان (۱۰ میلیارد)
    - total_shares = 1000
    - share_price محاسبه‌ای = 10,000,000 تومان (در save محاسبه می‌شود)
    """

    class Meta:
        model = Campaign

    sponsor = factory.SubFactory(SponsorFactory)
    title = factory.Sequence(lambda n: f"حرکت تستی شماره {n}")
    description = factory.Faker("paragraph", nb_sentences=3, locale="fa_IR")
    cover_image = factory.LazyFunction(lambda: _make_image_file("cover.png"))

    total_amount = 10_000_000_000
    total_shares = 1000

    status = CampaignStatus.DRAFT
    is_visible = False
    has_deadline = False


class PublishedCampaignFactory(CampaignFactory):
    """Campaign منتشرشده + قابل نمایش — آماده دریافت مشارکت."""

    status = CampaignStatus.PUBLISHED
    is_visible = True
    published_at = factory.LazyFunction(timezone.now)


class CampaignWithDeadlineFactory(PublishedCampaignFactory):
    """Campaign منتشرشده با مهلت زمانی (۳۰ روز آینده)."""

    has_deadline = True
    deadline = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(days=30)
    )


class CompletedCampaignFactory(PublishedCampaignFactory):
    """Campaign تکمیل‌شده — تمام سهم‌ها فروخته شدند."""

    status = CampaignStatus.COMPLETED
    purchased_shares = 1000
    purchased_amount = 10_000_000_000
    participant_count = 5
    completed_at = factory.LazyFunction(timezone.now)


class ClosedCampaignFactory(PublishedCampaignFactory):
    """Campaign بسته‌شده (deadline رسیده یا ادمین دستی بسته)."""

    status = CampaignStatus.CLOSED
    closed_at = factory.LazyFunction(timezone.now)


# ---------------------------------------------------------------------------
# CampaignImageFactory
# ---------------------------------------------------------------------------

class CampaignImageFactory(factory.django.DjangoModelFactory):
    """Factory برای تصاویر گالری حرکت."""

    class Meta:
        model = CampaignImage

    campaign = factory.SubFactory(PublishedCampaignFactory)
    image = factory.LazyFunction(lambda: _make_image_file("gallery.png"))
    alt_text = factory.Faker("sentence", nb_words=4, locale="fa_IR")
    display_order = factory.Sequence(lambda n: n)


# ---------------------------------------------------------------------------
# ParticipationFactory
# ---------------------------------------------------------------------------

class ParticipationFactory(factory.django.DjangoModelFactory):
    """
    Factory پایه برای Participation در وضعیت PENDING_PAYMENT.

    نکته: مقادیر share_price_snapshot و total_amount از campaign محاسبه می‌شوند.
    """

    class Meta:
        model = Participation

    campaign = factory.SubFactory(PublishedCampaignFactory)
    user = factory.SubFactory(UserFactory)
    share_count = 1
    status = ParticipationStatus.PENDING_PAYMENT

    @factory.lazy_attribute
    def share_price_snapshot(self) -> int:
        """قیمت سهم را از campaign در لحظه ساخت می‌گیرد."""
        return self.campaign.share_price

    @factory.lazy_attribute
    def total_amount(self) -> int:
        """مبلغ کل = تعداد سهم × قیمت لحظه‌ای."""
        return self.share_count * self.share_price_snapshot


class PaidParticipationFactory(ParticipationFactory):
    """Participation با وضعیت PAID — پرداخت موفق."""

    status = ParticipationStatus.PAID
    paid_at = factory.LazyFunction(timezone.now)


class FailedParticipationFactory(ParticipationFactory):
    """Participation با وضعیت FAILED — پرداخت ناموفق."""

    status = ParticipationStatus.FAILED


class ExpiredParticipationFactory(ParticipationFactory):
    """Participation با وضعیت EXPIRED — مدت اعتبار پرداخت تمام شد."""

    status = ParticipationStatus.EXPIRED


# ---------------------------------------------------------------------------
# PaymentFactory
# ---------------------------------------------------------------------------

class PaymentFactory(factory.django.DjangoModelFactory):
    """Factory پایه برای Payment در وضعیت PENDING."""

    class Meta:
        model = Payment

    participation = factory.SubFactory(ParticipationFactory)
    gateway_name = "sandbox"
    authority = factory.Sequence(lambda n: f"AUTH-TEST-{n:08d}")
    status = PaymentStatus.PENDING
    ip_address = "127.0.0.1"
    user_agent = "pytest-test-agent/1.0"

    @factory.lazy_attribute
    def user(self):
        """User را از participation می‌گیرد (denormalized)."""
        return self.participation.user

    @factory.lazy_attribute
    def amount(self) -> int:
        """مبلغ را از participation می‌گیرد."""
        return self.participation.total_amount


class SuccessPaymentFactory(PaymentFactory):
    """Payment با وضعیت SUCCESS — پرداخت تأییدشده."""

    status = PaymentStatus.SUCCESS
    participation = factory.SubFactory(PaidParticipationFactory)
    ref_id = factory.Sequence(lambda n: f"REF-{n:010d}")
    gateway_status = "100"
    paid_at = factory.LazyFunction(timezone.now)
    verified_at = factory.LazyFunction(timezone.now)


class FailedPaymentFactory(PaymentFactory):
    """Payment با وضعیت FAILED."""

    status = PaymentStatus.FAILED
    participation = factory.SubFactory(FailedParticipationFactory)
    gateway_status = "-1"
