"""
تست‌های همزمانی واقعی مالی — فقط PostgreSQL.

پس‌زمینه (آپکس ممیزی مستقل — یافتهٔ بحرانی ۳.۱):
    وقتی backend از `select_for_update` پشتیبانی نکند، جنگو عبارت FOR UPDATE
    را بی‌صدا از SQL حذف می‌کند — نه خطا می‌دهد، نه هشدار. تمام ۴۶ فراخوانی
    قفل ردیفی پروژه روی SQLite عملاً هیچ‌کاری نمی‌کردند و هیچ تستی این را
    نشان نمی‌داد. این تست‌ها همان مسیرهای داغ مالی را با دو thread واقعی و
    قفل واقعی (PostgreSQL) اجرا می‌کنند:

    ۱. رزرو آخرین سهم کمپین → نباید oversell شود.
    ۲. تأیید همزمان یک پرداخت → باید دقیقاً یک‌بار اعمال شود.
    ۳. تکمیل همزمان یک بازپرداخت → باید دقیقاً یک‌بار اعمال شود.
    ۴. تعیین همزمان جایزه R4J برای یک user+criminal → باید یک bounty فعال
       بماند.

خطرات thread و دیتابیس:
- هر thread اتصال خودش را باز می‌کند (اتصالات Django thread-local هستند) و
  در finally می‌بندد تا `teardown_databases` در پایان session گیر نکند.
- روی SQLite این تست‌ها اجرا نمی‌شوند (allow_module_level skip) — نه به‌خاطر
  اینکه باگ باشند، بلکه چون بدون قفل واقعی نتیجه‌شان نامعین است و به‌جای
  اثباتِ همزمانی، فقط flaky می‌شوند. CI روی PostgreSQL آن‌ها را اجرا می‌کند.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import pytest
from django.db import connection, connections

from apps.madadkar import services as madadkar_services
from apps.madadkar.choices import (
    ParticipationStatus,
    PaymentEventKind,
    PaymentStatus,
)
from apps.madadkar.models import PaymentEvent
from apps.madadkar.services import CampaignNotAcceptingSharesError, RefundWorkflowError

if connection.vendor != "postgresql":
    pytest.skip(
        "این تست‌ها فقط روی PostgreSQL معنادارند؛ روی SQLite قفل ردیفی بی‌صدا حذف می‌شود "
        "و نتیجهٔ race نامعین است. CI این فایل را روی PostgreSQL اجرا می‌کند.",
        allow_module_level=True,
    )

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
]


def _run_in_parallel(
    fn: Callable[[], object], count: int = 2, barrier_timeout: int = 30
) -> tuple[list[object], list[BaseException]]:
    """اجرای count نسخه از fn همزمان با یک barrier؛ جمع‌آوری نتایج/خطاها."""
    barrier = threading.Barrier(count)
    results: list[object] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait(timeout=barrier_timeout)
            outcome = fn()
            with lock:
                results.append(outcome)
        except Exception as exc:
            with lock:
                errors.append(exc)
        finally:
            # اتصال thread-local همین thread را ببند تا session teardown سالم بماند.
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads), "یک thread کامل نشد (بن‌بست یا timeout)"
    return results, errors


# ============================================================================
# ۱ — رزرو آخرین سهم: دو خریدار همزمان، فقط یکی باید سهم بگیرد
# ============================================================================


def test_share_reservation_concurrent_buyers_cannot_oversell() -> None:
    """
    دو thread همزمان آخرین سهم را می‌خواهند.

    بدون قفل ردیفی، هر دو thread «باقی‌مانده = ۱» را می‌بینند و هر دو رزرو
    می‌کنند (oversell). با قفل واقعی: یکی رزرو می‌کند و دیگری پس از commit
    اولی، کمپین را fully-funded می‌بیند و رد می‌شود.
    """
    from apps.madadkar.models import Participation
    from tests.factories.auth import UserFactory
    from tests.factories.madadkar import PublishedCampaignFactory

    campaign = PublishedCampaignFactory(total_shares=1, share_price=1_000)
    users = [UserFactory() for _ in range(2)]

    def attempt(user):
        return madadkar_services.initiate_participation(
            campaign=campaign,
            user=user,
            share_count=1,
            callback_url="https://example.test/payment/callback/",
        )

    results, errors = _run_in_parallel(lambda: attempt(users[0]), count=2)

    assert len(results) == 1, f"دقیقاً یک مشارکت باید موفق شود: {results}"
    assert len(errors) == 1, errors
    assert isinstance(errors[0], CampaignNotAcceptingSharesError), errors

    campaign.refresh_from_db()
    assert campaign.purchased_shares == 1, "فقط یک سهم باید خریداری/رزرو شده باشد"
    assert campaign.remaining_shares == 0
    assert (
        Participation.objects.filter(
            campaign=campaign, status=ParticipationStatus.PENDING_PAYMENT
        ).count()
        == 1
    ), "فقط یک مشارکت در انتظار پرداخت باید وجود داشته باشد"


# ============================================================================
# ۲ — تأیید همزمان یک پرداخت: فقط یک بار SUCCESS
# ============================================================================


def test_verify_payment_concurrent_verify_applies_success_exactly_once() -> None:
    """دو فراخوانی verify همزمان روی یک authority — فقط یک بار SUCCESS ثبت شود."""
    from tests.factories.auth import UserFactory
    from tests.factories.madadkar import (
        ParticipationFactory,
        PaymentFactory,
        PublishedCampaignFactory,
    )

    campaign = PublishedCampaignFactory(total_shares=10, share_price=1_000)
    participation = ParticipationFactory(
        campaign=campaign,
        user=UserFactory(),
        share_count=1,
        status=ParticipationStatus.PENDING_PAYMENT,
    )
    payment = PaymentFactory(
        participation=participation,
        status=PaymentStatus.PENDING,
        authority="AUTH-RACE-VERIFY-0001",
    )

    results, errors = _run_in_parallel(
        lambda: madadkar_services.verify_payment(authority=payment.authority),
        count=2,
    )

    assert errors == [], f"verify همزمان نباید خطا بدهد: {errors}"
    assert len(results) == 2, "هر دو فراخوانی باید Payment برگردانند (idempotent)"

    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCESS
    assert payment.ref_id, "پرداخت موفق باید ref_id از درگاه داشته باشد"

    participation.refresh_from_db()
    assert participation.status == ParticipationStatus.PAID

    campaign.refresh_from_db()
    assert campaign.purchased_shares == 1, "سهم باید دقیقاً یک‌بار شمرده شود، نه دوبار"

    success_events = PaymentEvent.objects.filter(
        payment=payment, event_kind=PaymentEventKind.VERIFY_SUCCESS
    ).count()
    assert success_events == 1, (
        f"رویداد VERIFY_SUCCESS باید یک‌بار ثبت شود (ثبت شده: {success_events})"
    )


# ============================================================================
# ۳ — تکمیل همزمان بازپرداخت: فقط یک بار اثر مالی
# ============================================================================


def test_refund_completion_concurrent_applies_financial_effect_once() -> None:
    """دو thread همزمان بازپرداخت تأییدشده را کامل می‌کنند؛ فقط یک‌بار اعمال شود."""
    from apps.madadkar.choices import RefundStatus
    from tests.factories.auth import UserFactory
    from tests.factories.madadkar import (
        ParticipationFactory,
        PaymentFactory,
        PublishedCampaignFactory,
    )

    campaign = PublishedCampaignFactory(total_shares=10, share_price=1_000)
    participation = ParticipationFactory(
        campaign=campaign,
        user=UserFactory(),
        share_count=2,
        status=ParticipationStatus.PAID,
    )
    payment = PaymentFactory(
        participation=participation,
        status=PaymentStatus.SUCCESS,
        authority="AUTH-RACE-REFUND-0001",
    )

    refund = madadkar_services.request_payment_refund(
        payment=payment,
        amount=payment.amount,
        requested_by=participation.user,
    )
    refund = madadkar_services.approve_payment_refund(refund=refund, reviewed_by=None)

    results, errors = _run_in_parallel(
        lambda: madadkar_services.complete_payment_refund(refund=refund, provider_ref_id="REF-OK"),
        count=2,
    )

    assert len(results) == 1, f"باید دقیقاً یک thread موفق باشد: {results}"
    assert len(errors) == 1 and isinstance(errors[0], RefundWorkflowError), errors

    refund.refresh_from_db()
    assert refund.status == RefundStatus.COMPLETED

    participation.refresh_from_db()
    assert participation.status == ParticipationStatus.REFUNDED

    completed_events = PaymentEvent.objects.filter(
        payment=payment, event_kind=PaymentEventKind.REFUND_COMPLETED
    ).count()
    assert completed_events == 1, (
        f"رویداد REFUND_COMPLETED باید یک‌بار ثبت شود (ثبت شده: {completed_events})"
    )

    campaign.refresh_from_db()
    assert campaign.purchased_shares == 0, "بعد از بازپرداخت کامل، سهم فروخته‌شده باید صفر شود"
    assert campaign.purchased_amount == 0


# ============================================================================
# ۴ — تعیین همزمان جایزه R4J: یک bounty فعال می‌ماند
# ============================================================================


def test_bounty_set_concurrent_creates_single_active_bounty() -> None:
    """دو thread همزمان برای یک user+criminal جایزه تعیین می‌کنند."""
    from apps.r4j.choices import BountyStatus
    from apps.r4j.models import R4JBounty
    from apps.r4j.services import set_or_update_bounty
    from tests.factories.auth import UserFactory
    from tests.factories.r4j import R4JCriminalPublishedFactory

    criminal = R4JCriminalPublishedFactory()
    user = UserFactory()

    results, errors = _run_in_parallel(
        lambda: set_or_update_bounty(criminal=criminal, user=user, amount_toman=500_000),
        count=2,
    )

    assert errors == [], f"تعیین همزمان جایزه نباید خطا بدهد: {errors}"
    assert len(results) == 2

    active = R4JBounty.objects.filter(criminal=criminal, user=user, status=BountyStatus.ACTIVE)
    assert active.count() == 1, f"فقط یک bounty فعال مجاز است (تعداد: {active.count()})"

    criminal.refresh_from_db()
    assert criminal.bounties_count == 1
    assert criminal.total_bounty_toman == active.get().amount_toman
