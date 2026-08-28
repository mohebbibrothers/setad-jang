"""Service layer for notification events, deliveries and preferences."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.notifications.choices import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEventStatus,
    NotificationPriority,
)
from apps.notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
    NotificationTemplate,
    render_template_string,
)
from apps.notifications.providers import NotificationDeliveryResult, get_notification_provider

logger = logging.getLogger(__name__)


class NotificationServiceError(Exception):
    """Base notification service exception."""


def _dedupe_recipients(recipients: Iterable[Any]) -> list[Any]:
    """Return recipients with duplicates removed, preserving input order.

    حذف تکراری‌ها فقط یک بهینه‌سازی نیست؛ پیش‌شرط درستی است. نسخهٔ قبلی از
    ``get_or_create`` استفاده می‌کرد که برخورد با unique constraint
    ``(event, recipient, channel)`` را بی‌صدا جذب می‌کرد. حالا که با
    ``bulk_create`` می‌نویسیم، تکراری بودن ورودی به ``IntegrityError`` منجر
    می‌شود. چون ``event`` تازه ساخته شده، تنها منبع ممکن برای برخورد همین
    ورودی تکراری است، پس یکتا کردن اینجا تضمین می‌کند برخوردی رخ ندهد.
    """
    seen: set[Any] = set()
    unique: list[Any] = []
    for recipient in recipients:
        marker = getattr(recipient, "pk", None)
        if marker is None:
            # کاربر ذخیره‌نشده — مثل قبل اجازه می‌دهیم لایه ORM خطا بدهد.
            unique.append(recipient)
            continue
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(recipient)
    return unique


@transaction.atomic
def create_notification_event(
    *,
    event_type: str,
    recipients: Iterable[Any],
    channels: Iterable[str] = (NotificationChannel.IN_APP,),
    payload: dict[str, Any] | None = None,
    actor: Any | None = None,
    aggregate_type: str = "",
    aggregate_id: str = "",
    priority: str = NotificationPriority.NORMAL,
) -> NotificationEvent:
    """Create event and pending deliveries for enabled recipient preferences.

    هزینهٔ کوئری
    -------------
    نسخهٔ قبلی برای هر جفت (گیرنده، کانال) پنج کوئری جدا می‌زد: خواندن
    ترجیح کاربر، خواندن قالب، ``get_or_create`` (SELECT + INSERT) و ثبت
    activity. برای یک broadcast به ۱۰۰۰ کاربر روی ۲ کانال یعنی حدود ۱۰٬۰۰۰
    کوئری داخل **یک** ``transaction.atomic`` — تراکنش ده‌ها ثانیه باز
    می‌ماند، ردیف‌ها قفل می‌شوند و worker عملاً از کار می‌افتد.

    نسخهٔ فعلی مستقل از تعداد گیرندگان، تعداد ثابتی کوئری می‌زند:
    یک INSERT برای رویداد، یک SELECT برای ترجیح‌ها، یک SELECT برای قالب‌ها،
    یک ``bulk_create`` برای تحویل‌ها و یک ``bulk_create`` برای activityها.
    """
    payload = payload or {}
    # ``dict.fromkeys`` ترتیب را حفظ می‌کند و تکراری‌ها را حذف می‌کند.
    channel_list = list(dict.fromkeys(channels))
    recipient_list = _dedupe_recipients(recipients)

    event = NotificationEvent.objects.create(
        event_type=event_type,
        actor=actor if getattr(actor, "pk", None) else None,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        priority=priority,
    )
    if not recipient_list or not channel_list:
        return event

    # یک کوئری برای همهٔ ترجیح‌ها. فقط ردیف‌های صریحاً غیرفعال اهمیت دارند،
    # چون نبودِ ردیف یعنی «مجاز» (همان رفتار ``_preference_enabled``).
    recipient_pks = [pk for pk in (getattr(r, "pk", None) for r in recipient_list) if pk is not None]
    muted: set[tuple[Any, str]] = set(
        NotificationPreference.objects.filter(
            user_id__in=recipient_pks,
            event_type=event_type,
            channel__in=channel_list,
            enabled=False,
        ).values_list("user_id", "channel"),
    )

    # یک کوئری برای همهٔ قالب‌ها. ``(code, channel)`` unique است پس هر کانال
    # حداکثر یک قالب دارد و نگاشت قطعی است.
    rendered: dict[str, tuple[str, str]] = {
        channel: render_notification(event_type=event_type, channel=channel, payload=payload, template=template)
        for channel, template in _templates_by_channel(event_type=event_type, channels=channel_list).items()
    }

    deliveries: list[NotificationDelivery] = []
    activity_recipients: list[Any] = []
    for recipient in recipient_list:
        for channel in channel_list:
            if (recipient.pk, channel) in muted:
                continue
            subject, body = rendered[channel]
            deliveries.append(
                NotificationDelivery(event=event, recipient=recipient, channel=channel, subject=subject, body=body),
            )
            activity_recipients.append(recipient)

    if not deliveries:
        return event

    NotificationDelivery.objects.bulk_create(deliveries)

    # import محلی برای شکستن وابستگی حلقوی بین notifications و activity.
    from apps.activity.services import record_activities_from_notification_event

    record_activities_from_notification_event(event=event, recipients=activity_recipients)
    return event


def _templates_by_channel(*, event_type: str, channels: list[str]) -> dict[str, NotificationTemplate | None]:
    """Fetch active templates for one event type keyed by channel, in one query."""
    found = {
        template.channel: template
        for template in NotificationTemplate.objects.filter(
            code=event_type,
            channel__in=channels,
            is_active=True,
        )
    }
    return {channel: found.get(channel) for channel in channels}


def render_notification(
    *,
    event_type: str,
    channel: str,
    payload: dict[str, Any],
    template: NotificationTemplate | None = None,
) -> tuple[str, str]:
    """Render notification subject/body from template or safe fallback.

    وقتی ``template`` داده شود هیچ کوئری‌ای زده نمی‌شود؛ این مسیری است که
    ``create_notification_event`` برای جلوگیری از N+1 استفاده می‌کند.
    فراخوانی بدون ``template`` رفتار قبلی (یک کوئری) را حفظ می‌کند تا
    امضای عمومی تابع سازگار بماند.
    """
    if template is None:
        template = NotificationTemplate.objects.filter(code=event_type, channel=channel, is_active=True).first()
    if template:
        return (
            render_template_string(template.subject_template, payload),
            render_template_string(template.body_template, payload),
        )
    title = str(payload.get("title") or event_type)
    body = str(payload.get("message") or title)
    return title, body


def dispatch_event(*, event: NotificationEvent) -> NotificationEvent:
    """Dispatch all pending deliveries for a notification event.

    ساختار سه‌فازی
    ----------------
    نسخهٔ قبلی کل کار را داخل یک ``transaction.atomic`` انجام می‌داد و در همان
    حال با providerهای بیرونی حرف می‌زد (SMTP، پنل پیامک، webhook). دو
    پیامد داشت که هر دو در production خطرناک‌اند:

    1. یک تراکنش دیتابیس به مدت مجموع تمام تماس‌های شبکه‌ای باز می‌ماند و
       روی جدولی که مسیر خواندن نوتیفیکیشن کاربر هم به آن می‌خورد قفل
       نگه می‌داشت.
    2. اگر چیزی وسط کار خطا می‌داد، تراکنش برمی‌گشت و تحویل‌ها دوباره
       ``PENDING`` می‌شدند — در حالی که ایمیل‌ها **واقعاً ارسال شده بودند**.
       تلاش بعدی همه را دوباره می‌فرستاد. rollback دیتابیس نمی‌تواند یک
       ایمیل ارسال‌شده را پس بگیرد.

    حالا: یک تراکنش کوتاه برای علامت‌گذاری شروع، سپس تماس‌های شبکه‌ای
    **بیرون از هر تراکنش**، سپس یک تراکنش کوتاه برای ثبت نتیجه با
    ``bulk_update``. خطای غیرمنتظرهٔ یک provider همان تحویل را ``FAILED``
    می‌کند و بقیه ادامه می‌یابند، پس یک کانال خراب کل دسته را از بین
    نمی‌برد.

    هزینهٔ کوئری هم ثابت شد: ``select_related`` روی گیرنده، N+1 قبلی در
    ``_recipient_address`` را حذف می‌کند و به‌جای یک ``save()`` برای هر
    تحویل، یک ``bulk_update`` انجام می‌شود.
    """
    with transaction.atomic():
        event.status = NotificationEventStatus.PROCESSING
        event.attempt_count += 1
        event.save(update_fields=["status", "attempt_count", "updated_at"])

    pending = list(
        event.deliveries.filter(status=NotificationDeliveryStatus.PENDING).select_related("recipient"),
    )
    sent = failed = 0
    for delivery in pending:
        # کش رابطهٔ معکوس را پر می‌کنیم تا ``delivery.event`` در
        # ``_recipient_address`` (مسیر webhook) کوئری اضافه نزند.
        delivery.event = event
        result = _send_delivery(delivery=delivery, event=event)
        delivery.provider = result.provider
        delivery.external_id = result.external_id
        if result.success:
            delivery.status = NotificationDeliveryStatus.SENT
            delivery.sent_at = timezone.now()
            sent += 1
        else:
            delivery.status = NotificationDeliveryStatus.FAILED
            delivery.error_message = result.error_message
            failed += 1

    with transaction.atomic():
        if pending:
            NotificationDelivery.objects.bulk_update(
                pending,
                ["provider", "external_id", "status", "sent_at", "error_message", "updated_at"],
            )
        event.status = NotificationEventStatus.SENT if failed == 0 else (NotificationEventStatus.PARTIAL if sent else NotificationEventStatus.FAILED)
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "processed_at", "updated_at"])
    return event


def _send_delivery(*, delivery: NotificationDelivery, event: NotificationEvent) -> NotificationDeliveryResult:
    """Send one delivery, converting an unexpected provider error into a failure result.

    providerهای موجود خطاهای مورد انتظارشان را خودشان به نتیجهٔ ناموفق
    تبدیل می‌کنند. این پوشش برای خطای *غیرمنتظره* است (کانال ناشناخته،
    خطای برنامه‌نویسی در provider) تا یک تحویل خراب باعث از دست رفتن نتیجهٔ
    تحویل‌های موفق همان دسته نشود.
    """
    try:
        return get_notification_provider(delivery.channel).send(
            recipient=_recipient_address(delivery),
            subject=delivery.subject,
            body=delivery.body,
            payload=event.payload,
        )
    except Exception as exc:
        logger.exception(
            "Notification delivery raised unexpectedly event_id=%s delivery_id=%s channel=%s",
            event.pk,
            delivery.pk,
            delivery.channel,
        )
        return NotificationDeliveryResult(
            success=False,
            provider=delivery.channel,
            error_message=type(exc).__name__,
        )


@transaction.atomic
def mark_delivery_read(*, delivery: NotificationDelivery, user: Any) -> NotificationDelivery:
    """Mark a user-owned delivery as read."""
    if delivery.recipient_id != user.pk:
        raise NotificationServiceError("این اعلان متعلق به کاربر جاری نیست.")
    delivery.status = NotificationDeliveryStatus.READ
    delivery.read_at = timezone.now()
    delivery.save(update_fields=["status", "read_at", "updated_at"])
    return delivery


@transaction.atomic
def mark_all_read(*, user: Any) -> int:
    """Mark all current user's deliveries as read."""
    now = timezone.now()
    updated = NotificationDelivery.objects.filter(recipient=user).exclude(status=NotificationDeliveryStatus.READ).update(status=NotificationDeliveryStatus.READ, read_at=now, updated_at=now)
    return int(updated)


@transaction.atomic
def set_preference(*, user: Any, event_type: str, channel: str, enabled: bool) -> NotificationPreference:
    """Set a user's preference for an event/channel pair."""
    preference, _created = NotificationPreference.objects.update_or_create(
        user=user,
        event_type=event_type,
        channel=channel,
        defaults={"enabled": enabled},
    )
    return preference


def _preference_enabled(*, user: Any, event_type: str, channel: str) -> bool:
    """Return whether a user allows the event/channel delivery."""
    preference = NotificationPreference.objects.filter(user=user, event_type=event_type, channel=channel).first()
    return True if preference is None else preference.enabled


def _recipient_address(delivery: NotificationDelivery) -> str:
    """Return recipient address based on delivery channel."""
    user = delivery.recipient
    if delivery.channel == NotificationChannel.EMAIL:
        return getattr(user, "email", "") or ""
    if delivery.channel == NotificationChannel.SMS:
        return getattr(user, "phone_number", "") or ""
    if delivery.channel == NotificationChannel.WEBHOOK:
        return str(delivery.event.payload.get("webhook_url", ""))
    return str(user.pk)
