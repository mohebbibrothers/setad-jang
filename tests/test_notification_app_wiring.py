"""Apex B2 cross-app notification wiring tests."""

from __future__ import annotations

import pytest
from django.test import override_settings

from apps.kindness_wall.models import KindnessContactReveal, KindnessMatch
from apps.kindness_wall.services import regenerate_matches_for_listing, reveal_contact
from apps.lms.services import create_skill_for_certificate
from apps.madadkar.services import initiate_participation, verify_payment
from apps.notifications.models import NotificationDelivery, NotificationEvent, NotificationTemplate
from apps.support_desk.services import add_admin_reply, resolve_ticket
from apps.tabyin.choices import ContentOrigin, SubmissionStatus
from apps.tabyin.services import approve_user_submission, reject_user_submission
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.kindness_wall import PublishedNeedListingFactory, PublishedOfferListingFactory
from tests.factories.lms import CertificateFactory
from tests.factories.madadkar import PublishedCampaignFactory
from tests.factories.support_desk import SupportTicketFactory
from tests.factories.tabyin import TabyinContentFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _ensure_notification_template_seeds(db):
    """بازسازی seed مایگریشن 0003 (idempotent).

    تست‌های تراکنشی (transaction=True) کل دیتابیس را flush می‌کنند — روی
    PostgreSQL این یعنی TRUNCATE — پس قالب‌های seedشده ممکن است غایب باشند
    و این assertion های مربوط به NotificationTemplate را مستقل از ترتیب
    اجرا می‌کند.
    """
    from tests.seed_helpers import reseed_notification_templates

    reseed_notification_templates()


@override_settings(NOTIFICATIONS_ASYNC_DISPATCH=False)
def test_support_reply_and_resolved_emit_in_app_notifications() -> None:
    """Support service events should notify ticket owner."""
    ticket = SupportTicketFactory(status="submitted")
    admin = AdminUserFactory()

    add_admin_reply(ticket=ticket, admin=admin, body="پاسخ پشتیبانی")
    resolve_ticket(ticket=ticket, admin=admin)

    event_types = set(NotificationEvent.objects.values_list("event_type", flat=True))
    assert {"support.reply", "support.resolved"}.issubset(event_types)
    assert NotificationDelivery.objects.filter(recipient=ticket.owner).count() >= 2


@override_settings(NOTIFICATIONS_ASYNC_DISPATCH=False)
def test_tabyin_approval_and_rejection_emit_notifications() -> None:
    """Tabyin review workflows should notify submitting user."""
    admin = AdminUserFactory()
    approved = TabyinContentFactory(
        origin=ContentOrigin.USER_SUBMITTED,
        submitted_by=UserFactory(),
        submission_status=SubmissionStatus.PENDING_REVIEW,
        title="محتوای تأییدی",
        is_active=False,
    )
    rejected = TabyinContentFactory(
        origin=ContentOrigin.USER_SUBMITTED,
        submitted_by=UserFactory(),
        submission_status=SubmissionStatus.PENDING_REVIEW,
        title="محتوای ردشده",
        is_active=False,
    )

    approve_user_submission(content=approved, admin=admin)
    reject_user_submission(content=rejected, admin=admin)

    assert NotificationEvent.objects.filter(
        event_type="tabyin.submission_approved", deliveries__recipient=approved.submitted_by
    ).exists()
    assert NotificationEvent.objects.filter(
        event_type="tabyin.submission_rejected", deliveries__recipient=rejected.submitted_by
    ).exists()


@override_settings(NOTIFICATIONS_ASYNC_DISPATCH=False)
def test_lms_certificate_issued_emits_notification_only_for_new_skill() -> None:
    """Certificate skill creation should notify once."""
    certificate = CertificateFactory()

    create_skill_for_certificate(certificate=certificate)
    create_skill_for_certificate(certificate=certificate)

    assert (
        NotificationEvent.objects.filter(
            event_type="lms.certificate_issued", deliveries__recipient=certificate.user
        ).count()
        == 1
    )


@override_settings(NOTIFICATIONS_ASYNC_DISPATCH=False)
def test_kindness_contact_reveal_and_high_match_emit_notifications() -> None:
    """Kindness Wall important events should notify listing owner."""
    source = PublishedNeedListingFactory(title="نیاز به برنامه نویس پایتون")
    target = PublishedOfferListingFactory(
        category=source.category, title="آموزش برنامه نویسی پایتون"
    )
    viewer = UserFactory()

    reveal = reveal_contact(listing=source, viewer=viewer)
    KindnessMatch.objects.create(source_listing=source, target_listing=target, score=95)
    regenerate_matches_for_listing(listing=source)

    assert KindnessContactReveal.objects.filter(pk=reveal.pk).exists()
    assert NotificationEvent.objects.filter(
        event_type="kindness.contact_revealed", deliveries__recipient=source.owner
    ).exists()
    assert NotificationEvent.objects.filter(
        event_type="kindness.high_match", deliveries__recipient=source.owner
    ).exists()
    assert NotificationTemplate.objects.filter(
        code="kindness.high_match", channel="in_app"
    ).exists()


@override_settings(NOTIFICATIONS_ASYNC_DISPATCH=False)
def test_madadkar_successful_payment_emits_notification() -> None:
    """Madadkar payment verification should notify paying user."""
    campaign = PublishedCampaignFactory(
        title="کمپین اعلان پرداخت", total_amount=100_000, total_shares=10, share_price=10_000
    )
    user = UserFactory()
    _participation, payment, _url = initiate_participation(
        campaign=campaign, user=user, share_count=1, callback_url="https://example.com/callback"
    )

    verify_payment(authority=payment.authority)

    assert NotificationEvent.objects.filter(
        event_type="madadkar.payment_success", deliveries__recipient=user
    ).exists()
