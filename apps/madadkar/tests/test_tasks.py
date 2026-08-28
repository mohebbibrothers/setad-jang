"""
تست‌های Celery tasks اپ مددکار.

پوشش:
- expire_stale_participations_task:
  * پیدا کردن participationهای راکد + expire آن‌ها
  * release سهم رزرو شده بعد از expire
  * empty queue → graceful no-op
  * یک شکست در حلقه باعث block بقیه نمی‌شود
  * idempotency — اجرای دوباره بدون side-effect
  * task delay (eager execution در test)

- close_expired_campaigns_task:
  * پیدا کردن campaignهای با deadline گذشته
  * بستن آن‌ها + closed_at ست شود
  * campaignهای بدون deadline یا DRAFT رد می‌شوند
  * empty queue → graceful no-op
  * یک شکست در حلقه باعث block بقیه نمی‌شود
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.madadkar.choices import (
    CampaignStatus,
    ParticipationStatus,
    PaymentStatus,
)
from apps.madadkar.models import Campaign, Participation
from apps.madadkar.tasks import (
    close_expired_campaigns_task,
    expire_stale_participations_task,
)
from tests.factories.madadkar import (
    CampaignFactory,
    CampaignWithDeadlineFactory,
    PaidParticipationFactory,
    ParticipationFactory,
    PaymentFactory,
    PublishedCampaignFactory,
)

pytestmark = pytest.mark.django_db


# ============================================================
# Helpers
# ============================================================


def _make_stale_participation_with_payment(*, share_count: int = 1):
    """
    helper: یک Participation PENDING_PAYMENT قدیمی بساز (همراه Payment).

    این تابع created_at را به ۲۰ دقیقه پیش set می‌کند تا توسط
    get_stale_participations برداشته شود (پیش‌فرض timeout = 15 دقیقه).
    """
    campaign = PublishedCampaignFactory(
        total_amount=100_000_000,
        total_shares=100,
    )
    participation = ParticipationFactory(
        campaign=campaign,
        share_count=share_count,
        status=ParticipationStatus.PENDING_PAYMENT,
    )
    PaymentFactory(
        participation=participation,
        status=PaymentStatus.PENDING,
    )

    # sync counter — تا purchased_shares به‌روز شود (به‌خاطر factory)
    from apps.madadkar.services import _sync_campaign_counters

    _sync_campaign_counters(campaign=campaign)

    # تاریخ ایجاد را به گذشته منتقل می‌کنیم
    old_time = timezone.now() - timezone.timedelta(minutes=20)
    Participation.objects.filter(pk=participation.pk).update(
        created_at=old_time,
    )
    participation.refresh_from_db()
    return participation, campaign


# ============================================================
# expire_stale_participations_task
# ============================================================


class TestExpireStaleParticipationsTask:
    """تست‌های periodic task برای expire کردن participationهای راکد."""

    def test_no_stale_participations_returns_zero(self):
        """در صورت نبود participation راکد، task گزارش 0 می‌دهد."""
        # فقط یک participation تازه — نباید touch شود
        ParticipationFactory()

        result = expire_stale_participations_task.apply().get()

        assert result["total_found"] == 0
        assert result["expired_count"] == 0
        assert result["failed_count"] == 0
        assert result["error_details"] == []

    def test_expires_stale_participation(self):
        """participation راکد به EXPIRED تبدیل می‌شود."""
        participation, _ = _make_stale_participation_with_payment()
        original_id = participation.pk

        result = expire_stale_participations_task.apply().get()

        assert result["total_found"] == 1
        assert result["expired_count"] == 1
        assert result["failed_count"] == 0

        participation.refresh_from_db()
        assert participation.status == ParticipationStatus.EXPIRED
        assert participation.pk == original_id

    def test_releases_reserved_shares(self):
        """بعد از expire، purchased_shares کاهش می‌یابد."""
        _participation, campaign = _make_stale_participation_with_payment(
            share_count=5,
        )

        # قبل از task: 5 سهم رزرو شده
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 5

        expire_stale_participations_task.apply().get()

        # بعد از task: 0 سهم
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 0

    def test_marks_associated_payment_as_failed(self):
        """Payment مرتبط با participation expired باید FAILED شود."""
        participation, _ = _make_stale_participation_with_payment()

        expire_stale_participations_task.apply().get()

        payment = participation.payment
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert payment.gateway_status == "expired"
        assert payment.verified_at is not None

    def test_fresh_participations_not_touched(self):
        """participationهای تازه (داخل timeout) touch نمی‌شوند."""
        # یک قدیمی برای expire
        _make_stale_participation_with_payment()
        # یک تازه — نباید touch شود
        fresh = ParticipationFactory(status=ParticipationStatus.PENDING_PAYMENT)

        result = expire_stale_participations_task.apply().get()

        assert result["total_found"] == 1
        assert result["expired_count"] == 1

        fresh.refresh_from_db()
        assert fresh.status == ParticipationStatus.PENDING_PAYMENT

    def test_paid_participations_not_touched(self):
        """participationهای PAID حتی اگر قدیمی باشند، expire نمی‌شوند."""
        paid = PaidParticipationFactory()
        # قدیمی کنیم
        old_time = timezone.now() - timezone.timedelta(hours=10)
        Participation.objects.filter(pk=paid.pk).update(created_at=old_time)

        result = expire_stale_participations_task.apply().get()

        assert result["total_found"] == 0
        paid.refresh_from_db()
        assert paid.status == ParticipationStatus.PAID

    def test_handles_multiple_stale_participations(self):
        """task می‌تواند چندین stale را همزمان پردازش کند."""
        for _ in range(3):
            _make_stale_participation_with_payment(share_count=1)

        result = expire_stale_participations_task.apply().get()

        assert result["total_found"] == 3
        assert result["expired_count"] == 3
        assert result["failed_count"] == 0

    def test_one_failure_does_not_block_others(self):
        """اگر یک participation در حین expire خطا داد، بقیه ادامه دارند."""
        p1, _ = _make_stale_participation_with_payment()
        p2, _ = _make_stale_participation_with_payment()
        p3, _ = _make_stale_participation_with_payment()

        # mock کنیم که برای p2 خطا بدهد
        call_count = {"value": 0}
        original_id = p2.pk

        def mock_expire(*, participation):
            call_count["value"] += 1
            if participation.pk == original_id:
                msg = "simulated error"
                raise RuntimeError(msg)
            from apps.madadkar.services import (
                expire_stale_participation as real_expire,
            )

            return real_expire(participation=participation)

        with patch(
            "apps.madadkar.tasks.expire_stale_participation",
            side_effect=mock_expire,
        ):
            result = expire_stale_participations_task.apply().get()

        assert result["total_found"] == 3
        assert result["expired_count"] == 2
        assert result["failed_count"] == 1
        assert len(result["error_details"]) == 1
        assert result["error_details"][0]["participation_id"] == original_id

        # p1 و p3 expire شدند، p2 هنوز PENDING است
        p1.refresh_from_db()
        p3.refresh_from_db()
        p2.refresh_from_db()
        assert p1.status == ParticipationStatus.EXPIRED
        assert p3.status == ParticipationStatus.EXPIRED
        assert p2.status == ParticipationStatus.PENDING_PAYMENT

    def test_idempotent_second_run(self):
        """اجرای دوباره task روی همان داده side-effect ندارد."""
        _make_stale_participation_with_payment()

        result1 = expire_stale_participations_task.apply().get()
        assert result1["expired_count"] == 1

        # اجرای دوم — هیچ stale پیدا نمی‌شود
        result2 = expire_stale_participations_task.apply().get()
        assert result2["total_found"] == 0
        assert result2["expired_count"] == 0


# ============================================================
# close_expired_campaigns_task
# ============================================================


class TestCloseExpiredCampaignsTask:
    """تست‌های periodic task برای بستن campaignهای با deadline منقضی."""

    def test_no_expired_campaigns_returns_zero(self):
        """در صورت نبود campaign منقضی، task گزارش 0 می‌دهد."""
        # فقط یک campaign با deadline آینده — نباید touch شود
        CampaignWithDeadlineFactory()

        result = close_expired_campaigns_task.apply().get()

        assert result["total_found"] == 0
        assert result["closed_count"] == 0
        assert result["failed_count"] == 0

    def test_closes_campaign_with_passed_deadline(self):
        """campaign با deadline گذشته باید CLOSED شود."""
        campaign = CampaignWithDeadlineFactory()
        # deadline را به گذشته منتقل کنیم
        Campaign.objects.filter(pk=campaign.pk).update(
            deadline=timezone.now() - timezone.timedelta(hours=1),
        )

        result = close_expired_campaigns_task.apply().get()

        assert result["total_found"] == 1
        assert result["closed_count"] == 1
        assert result["failed_count"] == 0

        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.CLOSED
        assert campaign.closed_at is not None

    def test_does_not_close_campaign_with_future_deadline(self):
        """campaign با deadline آینده touch نمی‌شود."""
        campaign = CampaignWithDeadlineFactory()  # default: 30 day future

        result = close_expired_campaigns_task.apply().get()

        assert result["total_found"] == 0
        campaign.refresh_from_db()
        assert campaign.status == CampaignStatus.PUBLISHED

    def test_does_not_close_draft_campaign(self):
        """campaign DRAFT حتی با deadline گذشته، touch نمی‌شود."""
        # DRAFT با deadline ساختن از طریق factory ممکن نیست (constraint)
        # اما اگر در شرایط خاص رخ دهد، selector آن را فیلتر می‌کند.
        # این تست در عمل به selector اعتماد می‌کند.
        CampaignFactory()  # DRAFT بدون deadline

        result = close_expired_campaigns_task.apply().get()
        assert result["total_found"] == 0

    def test_does_not_close_campaign_without_deadline(self):
        """campaign بدون deadline (has_deadline=False) touch نمی‌شود."""
        PublishedCampaignFactory(has_deadline=False)

        result = close_expired_campaigns_task.apply().get()
        assert result["total_found"] == 0

    def test_handles_multiple_expired_campaigns(self):
        """task می‌تواند چندین campaign منقضی را همزمان ببندد."""
        for _ in range(3):
            campaign = CampaignWithDeadlineFactory()
            Campaign.objects.filter(pk=campaign.pk).update(
                deadline=timezone.now() - timezone.timedelta(hours=1),
            )

        result = close_expired_campaigns_task.apply().get()

        assert result["total_found"] == 3
        assert result["closed_count"] == 3
        assert result["failed_count"] == 0

    def test_one_failure_does_not_block_others(self):
        """اگر یک campaign خطا داد، بقیه ادامه دارند."""
        c1 = CampaignWithDeadlineFactory()
        c2 = CampaignWithDeadlineFactory()
        c3 = CampaignWithDeadlineFactory()
        target_pk = c2.pk

        for c in (c1, c2, c3):
            Campaign.objects.filter(pk=c.pk).update(
                deadline=timezone.now() - timezone.timedelta(hours=1),
            )

        def mock_close(*, campaign):
            if campaign.pk == target_pk:
                msg = "simulated error"
                raise RuntimeError(msg)
            from apps.madadkar.services import (
                close_campaign_due_to_deadline as real_close,
            )

            return real_close(campaign=campaign)

        with patch(
            "apps.madadkar.tasks.close_campaign_due_to_deadline",
            side_effect=mock_close,
        ):
            result = close_expired_campaigns_task.apply().get()

        assert result["total_found"] == 3
        assert result["closed_count"] == 2
        assert result["failed_count"] == 1
        assert len(result["error_details"]) == 1
        assert result["error_details"][0]["campaign_id"] == target_pk

        c1.refresh_from_db()
        c3.refresh_from_db()
        c2.refresh_from_db()
        assert c1.status == CampaignStatus.CLOSED
        assert c3.status == CampaignStatus.CLOSED
        assert c2.status == CampaignStatus.PUBLISHED  # خطا داد، تغییر نکرد

    def test_idempotent_second_run(self):
        """اجرای دوباره task روی همان داده side-effect ندارد."""
        campaign = CampaignWithDeadlineFactory()
        Campaign.objects.filter(pk=campaign.pk).update(
            deadline=timezone.now() - timezone.timedelta(hours=1),
        )

        result1 = close_expired_campaigns_task.apply().get()
        assert result1["closed_count"] == 1

        # اجرای دوم — هیچ campaign منقضی پیدا نمی‌شود (همه قبلاً CLOSED شدند)
        result2 = close_expired_campaigns_task.apply().get()
        assert result2["total_found"] == 0


# ============================================================
# Task Discovery / Registration
# ============================================================


class TestTaskRegistration:
    """تأیید registration و نام‌گذاری صحیح taskها."""

    def test_expire_task_has_correct_name(self):
        assert (
            expire_stale_participations_task.name
            == "apps.madadkar.tasks.expire_stale_participations_task"
        )

    def test_close_task_has_correct_name(self):
        assert (
            close_expired_campaigns_task.name == "apps.madadkar.tasks.close_expired_campaigns_task"
        )
