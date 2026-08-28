"""Domain-level notification helpers for cross-app event wiring."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction

from apps.notifications.choices import NotificationChannel, NotificationPriority
from apps.notifications.services import create_notification_event, dispatch_event
from apps.notifications.tasks import dispatch_notification_event_task


def emit_domain_notification(
    *,
    event_type: str,
    recipient: Any,
    payload: dict[str, Any],
    actor: Any | None = None,
    aggregate_type: str = "",
    aggregate_id: str = "",
    channels: list[str] | None = None,
    priority: str = NotificationPriority.NORMAL,
):
    """Create a domain notification event and schedule dispatch after commit."""
    selected_channels = channels or _default_channels(priority=priority)
    event = create_notification_event(
        event_type=event_type,
        recipients=[recipient],
        channels=selected_channels,
        payload=payload,
        actor=actor,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        priority=priority,
    )

    def _dispatch() -> None:
        if getattr(settings, "NOTIFICATIONS_ASYNC_DISPATCH", True):
            dispatch_notification_event_task.delay(event.pk)
        else:
            dispatch_event(event=event)

    transaction.on_commit(_dispatch)
    return event


def _default_channels(*, priority: str) -> list[str]:
    """Return default channels for domain notifications."""
    channels = [NotificationChannel.IN_APP]
    if getattr(settings, "NOTIFICATIONS_EMAIL_ENABLED", False):
        channels.append(NotificationChannel.EMAIL)
    if priority == NotificationPriority.URGENT and getattr(
        settings, "NOTIFICATIONS_SMS_ENABLED", False
    ):
        channels.append(NotificationChannel.SMS)
    return channels


def notify_support_reply(*, ticket, message) -> None:
    """Notify a user about an admin reply to a support ticket."""
    emit_domain_notification(
        event_type="support.reply",
        recipient=ticket.owner,
        actor=message.author,
        aggregate_type="support_ticket",
        aggregate_id=ticket.ticket_number,
        payload={
            "title": "پاسخ جدید پشتیبانی",
            "message": message.body,
            "ticket_number": ticket.ticket_number,
            "subject": ticket.subject,
        },
    )


def notify_support_resolved(*, ticket, actor) -> None:
    """Notify a user that their support ticket was resolved."""
    emit_domain_notification(
        event_type="support.resolved",
        recipient=ticket.owner,
        actor=actor,
        aggregate_type="support_ticket",
        aggregate_id=ticket.ticket_number,
        payload={
            "title": "تیکت شما حل شد",
            "ticket_number": ticket.ticket_number,
            "subject": ticket.subject,
        },
    )


def notify_public_report_status_changed(*, report, actor) -> None:
    """Notify report owner when a public report status changes."""
    if not getattr(report, "created_by_id", None):
        return
    emit_domain_notification(
        event_type="public_report.status_changed",
        recipient=report.created_by,
        actor=actor,
        aggregate_type="public_report",
        aggregate_id=str(report.pk),
        payload={
            "title": "وضعیت گزارش شما تغییر کرد",
            "tracking_code": report.tracking_code,
            "status": report.status,
        },
    )


def notify_tabyin_submission_reviewed(*, submission, actor, approved: bool) -> None:
    """Notify a user that their Tabyin submission was reviewed."""
    emit_domain_notification(
        event_type="tabyin.submission_approved" if approved else "tabyin.submission_rejected",
        recipient=submission.submitted_by,
        actor=actor,
        aggregate_type="tabyin_content",
        aggregate_id=str(submission.pk),
        payload={
            "title": "نتیجه بررسی محتوای تبیین",
            "content_title": submission.title,
            "approved": approved,
        },
    )


def notify_madadkar_payment_success(*, payment) -> None:
    """Notify user after a successful Madadkar payment verification."""
    user = payment.participation.user
    emit_domain_notification(
        event_type="madadkar.payment_success",
        recipient=user,
        actor=user,
        aggregate_type="madadkar_payment",
        aggregate_id=str(payment.pk),
        payload={
            "title": "پرداخت شما با موفقیت ثبت شد",
            "campaign_title": payment.participation.campaign.title,
            "amount": payment.amount,
            "ref_id": payment.ref_id,
        },
        priority=NotificationPriority.HIGH,
    )


def notify_lms_certificate_issued(*, certificate) -> None:
    """Notify user when an LMS certificate is issued."""
    emit_domain_notification(
        event_type="lms.certificate_issued",
        recipient=certificate.user,
        actor=certificate.user,
        aggregate_type="lms_certificate",
        aggregate_id=str(certificate.pk),
        payload={
            "title": "مدرک آموزشی شما صادر شد",
            "course_title": certificate.course_title_snapshot,
            "certificate_code": certificate.certificate_code,
        },
    )


def notify_kindness_contact_revealed(*, reveal) -> None:
    """Notify listing owner when their contact phone is revealed."""
    emit_domain_notification(
        event_type="kindness.contact_revealed",
        recipient=reveal.listing_owner,
        actor=reveal.viewer,
        aggregate_type="kindness_listing",
        aggregate_id=str(reveal.listing_id),
        payload={"title": "شماره تماس آگهی شما مشاهده شد", "listing_title": reveal.listing.title},
    )


def notify_kindness_high_match(*, source_listing, match) -> None:
    """Notify listing owner when a high-score match is generated."""
    if match.score < getattr(settings, "KINDNESS_MATCH_NOTIFICATION_THRESHOLD", 80):
        return
    emit_domain_notification(
        event_type="kindness.high_match",
        recipient=source_listing.owner,
        actor=source_listing.owner,
        aggregate_type="kindness_match",
        aggregate_id=str(match.pk),
        payload={
            "title": "پیشنهاد تطبیق جدید",
            "listing_title": source_listing.title,
            "score": match.score,
        },
    )
