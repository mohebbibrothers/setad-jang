"""Service layer for user activity timeline."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.activity.choices import ActivityVerb, ActivityVisibility
from apps.activity.models import UserActivity

_EVENT_VERB_MAP = {
    "support.reply": ActivityVerb.REPLIED,
    "support.resolved": ActivityVerb.RESOLVED,
    "public_report.status_changed": ActivityVerb.UPDATED,
    "tabyin.submission_approved": ActivityVerb.APPROVED,
    "tabyin.submission_rejected": ActivityVerb.REJECTED,
    "madadkar.payment_success": ActivityVerb.PAID,
    "lms.certificate_issued": ActivityVerb.ISSUED,
    "kindness.contact_revealed": ActivityVerb.REVEALED,
    "kindness.high_match": ActivityVerb.MATCHED,
}


def infer_app_label(event_type: str, aggregate_type: str = "") -> str:
    """Infer source app label from event or aggregate type."""
    if event_type.startswith("support."):
        return "support_desk"
    if event_type.startswith("tabyin."):
        return "tabyin"
    if event_type.startswith("madadkar."):
        return "madadkar"
    if event_type.startswith("lms."):
        return "lms"
    if event_type.startswith("kindness."):
        return "kindness_wall"
    if event_type.startswith("public_report."):
        return "public_reports"
    if event_type.startswith("r4j."):
        return "r4j"
    if aggregate_type:
        return aggregate_type.split("_", 1)[0]
    return "platform"


@transaction.atomic
def record_activity(
    *,
    user: Any,
    event_type: str,
    title: str,
    summary: str = "",
    actor: Any | None = None,
    aggregate_type: str = "",
    aggregate_id: str = "",
    app_label: str = "",
    verb: str | None = None,
    visibility: str = ActivityVisibility.PRIVATE,
    metadata: dict[str, Any] | None = None,
) -> UserActivity:
    """Record one user activity timeline event."""
    if not getattr(user, "pk", None):
        raise ValueError("Activity user must be persisted.")
    return UserActivity.objects.create(
        user=user,
        actor=actor if getattr(actor, "pk", None) else None,
        event_type=event_type,
        app_label=app_label or infer_app_label(event_type, aggregate_type),
        verb=verb or _EVENT_VERB_MAP.get(event_type, ActivityVerb.NOTIFIED),
        title=title[:260],
        summary=summary,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        visibility=visibility,
        metadata=metadata or {},
    )


def record_activity_from_notification_event(*, event, recipient) -> UserActivity:
    """Create an activity entry from a notification event payload."""
    payload = event.payload or {}
    title = str(payload.get("title") or event.event_type)
    summary = str(payload.get("message") or payload.get("subject") or "")
    return record_activity(
        user=recipient,
        actor=event.actor,
        event_type=event.event_type,
        title=title,
        summary=summary,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        metadata={"notification_event_id": event.pk, **payload},
    )


def build_activity_from_notification_event(*, event, recipient) -> UserActivity:
    """Build (without saving) the activity row for one notification recipient.

    این تابع دقیقاً همان فیلدهایی را می‌سازد که
    ``record_activity_from_notification_event`` می‌ساخت، ولی چیزی را ذخیره
    نمی‌کند. جدا کردن «ساختن» از «ذخیره کردن» همان چیزی است که اجازه می‌دهد
    فن‌اوت نوتیفیکیشن به‌جای یک INSERT به‌ازای هر گیرنده، یک ``bulk_create``
    واحد بزند.
    """
    if not getattr(recipient, "pk", None):
        raise ValueError("Activity user must be persisted.")
    payload = event.payload or {}
    title = str(payload.get("title") or event.event_type)
    summary = str(payload.get("message") or payload.get("subject") or "")
    aggregate_type = event.aggregate_type
    event_type = event.event_type
    return UserActivity(
        user=recipient,
        actor=event.actor if getattr(event.actor, "pk", None) else None,
        event_type=event_type,
        app_label=infer_app_label(event_type, aggregate_type),
        verb=_EVENT_VERB_MAP.get(event_type, ActivityVerb.NOTIFIED),
        title=title[:260],
        summary=summary,
        aggregate_type=aggregate_type,
        aggregate_id=event.aggregate_id,
        visibility=ActivityVisibility.PRIVATE,
        metadata={"notification_event_id": event.pk, **payload},
    )


def record_activities_from_notification_event(*, event, recipients) -> list[UserActivity]:
    """Create activity rows for many notification recipients in a single query.

    ترتیب و تعداد ردیف‌ها عمداً برابر رفتار قبلی نگه داشته شده: یک ردیف
    فعالیت به‌ازای هر تحویل ساخته‌شده، یعنی اگر یک گیرنده روی دو کانال
    اعلان بگیرد دو ردیف می‌گیرد. تغییر این معنا خارج از محدودهٔ این اصلاح
    است و باید جداگانه تصمیم‌گیری شود.
    """
    activities = [
        build_activity_from_notification_event(event=event, recipient=recipient)
        for recipient in recipients
    ]
    if not activities:
        return []
    return UserActivity.objects.bulk_create(activities)
