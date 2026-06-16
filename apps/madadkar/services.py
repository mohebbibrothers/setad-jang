"""
Services اپ مددکار — business logic لایه.

تمام عملیات mutation از این لایه عبور می‌کنند تا:
- transaction safety تضمین شود
- logging consistent بماند
- audit hooks در یک نقطه centralize شوند
- business rules در یک مرجع تمیز قرار بگیرند

بخش‌ها:
1. Exceptions — خطاهای دامنه
2. Helpers — توابع کمکی استخراج پیام و sync counters
3. Sponsor services — CRUD
4. Campaign services — CRUD + lifecycle + edit rules
5. Campaign image services — gallery management
6. Participation services — initiate + share reservation (concurrency-safe)
7. Payment services — verify + idempotency + amount tampering protection
8. Maintenance services — expire stale participations + close expired campaigns

نکات معماری حیاتی:
- بعد از اولین Participation موفق (PAID)، فیلدهای مالی حرکت قفل می‌شوند.
- initiate_participation: select_for_update روی Campaign + رزرو سهم پیش از redirect.
- verify_payment: idempotent — اگر قبلاً SUCCESS بوده، بدون تغییر برمی‌گردد.
- amount tampering: مبلغ تأیید‌شده توسط گیت‌وی با مبلغ stored مقایسه می‌شود.
  در صورت ناهماهنگی، Payment در یک atomic block جداگانه FAILED می‌شود (commit
  می‌گردد) و سپس exception raise می‌شود. این تضمین می‌کند security event
  حتماً در DB ثبت گردد.
- counter sync مبتنی بر source-of-truth: SUM از Participationها (نه delta).
- verify_payment با @transaction.atomic decorate نشده — به جای آن از inner
  atomic blocks استفاده می‌کند تا I/O به provider (slow) خارج از transaction
  باشد و در سناریوی amount mismatch تغییرات security commit شوند.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.madadkar.choices import (
    CampaignStatus,
    ParticipationStatus,
    PaymentEventKind,
    PaymentStatus,
    ReconciliationItemStatus,
    ReconciliationStatus,
)
from apps.madadkar.models import (
    Campaign,
    CampaignImage,
    Participation,
    Payment,
    PaymentEvent,
    PaymentReconciliationBatch,
    PaymentReconciliationItem,
    Sponsor,
)
from apps.madadkar.payment_providers import get_payment_provider
from apps.madadkar.validators import (
    validate_share_count,
    validate_share_price_divisibility,
    validate_total_amount,
    validate_total_shares,
)

logger = logging.getLogger("apps.madadkar")


# ===========================================================================
# Exceptions
# ===========================================================================

class MadadkarServiceError(Exception):
    """خطای پایه service layer مددکار."""


# ── Sponsor exceptions
class SponsorInUseError(MadadkarServiceError):
    """تلاش برای حذف Sponsor که دارای حرکت فعال است."""


class SponsorInvalidDataError(MadadkarServiceError):
    """داده‌های ورودی برای ساخت/ویرایش Sponsor نامعتبر است (مثل duplicate name)."""


# ── Campaign exceptions
class CampaignInvalidStateError(MadadkarServiceError):
    """تلاش برای transition غیرمجاز در lifecycle حرکت."""


class CampaignFieldLockedError(MadadkarServiceError):
    """تلاش برای ویرایش فیلدی که بعد از اولین پرداخت قفل شده است."""


class CampaignInvalidDataError(MadadkarServiceError):
    """داده‌های ورودی برای ساخت/ویرایش حرکت نامعتبر است."""


# ── Participation / Payment exceptions
class CampaignNotAcceptingSharesError(MadadkarServiceError):
    """حرکت در حال پذیرش سهم نیست (DRAFT, COMPLETED, CLOSED, expired)."""


class InsufficientSharesError(MadadkarServiceError):
    """تعداد سهم درخواستی بیشتر از سهم باقی‌مانده است."""


class InvalidShareCountError(MadadkarServiceError):
    """تعداد سهم درخواستی نامعتبر است."""


class PaymentGatewayError(MadadkarServiceError):
    """خطا در ارتباط با درگاه پرداخت یا پاسخ نامعتبر از سمت آن."""


class PaymentNotFoundError(MadadkarServiceError):
    """Payment با authority داده‌شده یافت نشد."""


class PaymentAmountMismatchError(MadadkarServiceError):
    """مبلغ تأیید‌شده توسط درگاه با مبلغ stored برابر نیست (تهدید tampering)."""


# ===========================================================================
# Helpers
# ===========================================================================

def _extract_django_validation_message(exc: DjangoValidationError) -> str:
    """
    استخراج اولین پیام معنادار از یک Django ValidationError.

    این helper پاسخ‌های 500 ناشی از ValidationError نادیده‌گرفته‌شده را
    به پیام‌های قابل نمایش به کاربر تبدیل می‌کند.
    """
    if hasattr(exc, "message_dict") and exc.message_dict:
        first_field = next(iter(exc.message_dict))
        messages = exc.message_dict[first_field]
        if messages:
            return str(messages[0])

    if hasattr(exc, "messages") and exc.messages:
        return str(exc.messages[0])

    return "داده‌های ورودی نامعتبر است."


def _has_paid_participations(campaign: Campaign) -> bool:
    """آیا حرکت دارای حداقل یک Participation با وضعیت PAID است؟"""
    return campaign.participations.filter(
        status=ParticipationStatus.PAID,
    ).exists()


def _sync_campaign_counters(*, campaign: Campaign) -> Campaign:
    """
    محاسبه و sync کردن counterهای denormalized یک حرکت.

    این تابع source-of-truth-based است: مقادیر را از روی Participationها
    دوباره محاسبه می‌کند، نه delta-based. این یعنی حتی اگر در جایی delta
    اشتباه شود، یک فراخوانی این تابع آن را تصحیح می‌کند.

    محاسبات:
    - purchased_shares: SUM از share_count برای PAID + PENDING_PAYMENT
      (PENDING رزرو شده محسوب می‌شود تا oversell نشود)
    - purchased_amount: SUM از total_amount فقط برای PAID (مبلغ واقعی)
    - participant_count: COUNT DISTINCT user_id برای PAID

    باید با transaction.atomic فراخوانی شود و در صورت نیاز
    select_for_update روی campaign اعمال شده باشد.
    """
    aggregates = campaign.participations.filter(
        status__in=[
            ParticipationStatus.PAID,
            ParticipationStatus.PENDING_PAYMENT,
        ],
    ).aggregate(
        reserved_shares=Sum("share_count"),
    )

    paid_aggregates = campaign.participations.filter(
        status=ParticipationStatus.PAID,
    ).aggregate(
        paid_amount=Sum("total_amount"),
        unique_users=Count("user_id", distinct=True),
    )

    campaign.purchased_shares = aggregates["reserved_shares"] or 0
    campaign.purchased_amount = paid_aggregates["paid_amount"] or 0
    campaign.participant_count = paid_aggregates["unique_users"] or 0
    campaign.save(
        update_fields=[
            "purchased_shares",
            "purchased_amount",
            "participant_count",
            "updated_at",
        ],
    )

    logger.info(
        "Madadkar campaign counters synced campaign_id=%s shares=%s amount=%s users=%s",
        campaign.pk,
        campaign.purchased_shares,
        campaign.purchased_amount,
        campaign.participant_count,
    )
    return campaign


def _is_campaign_open_for_participation(campaign: Campaign) -> tuple[bool, str]:
    """
    بررسی اینکه آیا حرکت در لحظه فعلی قابل دریافت سهم است.

    Returns:
        (is_open, reason): اگر باز نیست، reason پیام فارسی قابل نمایش است.
    """
    if not campaign.is_active:
        return False, "این حرکت غیرفعال شده است."

    if not campaign.is_visible:
        return False, "این حرکت در حال حاضر قابل مشارکت نیست."

    if campaign.status == CampaignStatus.DRAFT:
        return False, "این حرکت هنوز منتشر نشده است."

    if campaign.status == CampaignStatus.COMPLETED:
        return False, "این حرکت تکمیل شده و سهم بیشتری قابل خرید نیست."

    if campaign.status == CampaignStatus.CLOSED:
        return False, "این حرکت بسته شده است."

    if (
        campaign.has_deadline
        and campaign.deadline is not None
        and campaign.deadline <= timezone.now()
    ):
        return False, "مهلت این حرکت به پایان رسیده است."

    if campaign.is_fully_funded:
        return False, "تمام سهم‌های این حرکت رزرو شده است."

    return True, ""


def _record_payment_event(
    *,
    payment: Payment,
    event_kind: str,
    previous_status: str = "",
    new_status: str = "",
    metadata: dict[str, Any] | None = None,
) -> PaymentEvent:
    """
    ثبت append-only رویداد مالی برای reconciliation و forensic tracing.

    Payment آخرین وضعیت را نگه می‌دارد؛ PaymentEvent مسیر transitionها را ثبت
    می‌کند. این helper باید داخل همان transaction تغییر وضعیت payment فراخوانی
    شود تا ledger و state اصلی با هم commit شوند.
    """
    event = PaymentEvent.objects.create(
        payment=payment,
        event_kind=event_kind,
        previous_status=previous_status,
        new_status=new_status,
        amount=payment.amount,
        gateway_status=payment.gateway_status,
        ref_id=payment.ref_id,
        metadata=metadata or {},
    )
    logger.info(
        "Madadkar payment event recorded payment_id=%s event_id=%s kind=%s previous=%s new=%s",
        payment.pk,
        event.pk,
        event_kind,
        previous_status,
        new_status,
    )
    return event


# ===========================================================================
# Sponsor services
# ===========================================================================

@transaction.atomic
def create_sponsor(*, name: str, logo: Any = None) -> Sponsor:
    """
    ساخت یک Sponsor جدید.

    Raises:
        SponsorInvalidDataError: داده‌ها نامعتبر (مثل duplicate name).
    """
    sponsor = Sponsor(name=name)
    if logo is not None:
        sponsor.logo = logo

    try:
        sponsor.full_clean()
    except DjangoValidationError as exc:
        raise SponsorInvalidDataError(_extract_django_validation_message(exc)) from exc

    sponsor.save()

    logger.info(
        "Madadkar sponsor created sponsor_id=%s name=%s",
        sponsor.pk,
        sponsor.name,
    )
    return sponsor


@transaction.atomic
def update_sponsor(*, sponsor: Sponsor, **fields: Any) -> Sponsor:
    """
    آپدیت فیلدهای یک Sponsor.

    Raises:
        SponsorInvalidDataError: داده‌ها نامعتبر.
    """
    allowed = {"name", "logo"}
    update_fields: list[str] = []

    for field_name, value in fields.items():
        if field_name not in allowed:
            continue
        setattr(sponsor, field_name, value)
        update_fields.append(field_name)

    if not update_fields:
        return sponsor

    try:
        sponsor.full_clean()
    except DjangoValidationError as exc:
        raise SponsorInvalidDataError(_extract_django_validation_message(exc)) from exc

    update_fields.append("updated_at")
    sponsor.save(update_fields=update_fields)

    logger.info(
        "Madadkar sponsor updated sponsor_id=%s fields=%s",
        sponsor.pk,
        update_fields,
    )
    return sponsor


@transaction.atomic
def delete_sponsor(*, sponsor: Sponsor) -> None:
    """
    حذف نرم Sponsor.

    Raises:
        SponsorInUseError: اگر Sponsor دارای حرکت غیر DRAFT باشد.
    """
    active_campaigns_exist = Campaign.objects.filter(
        sponsor=sponsor,
    ).exclude(status=CampaignStatus.DRAFT).exists()

    if active_campaigns_exist:
        msg = "این مددکار دارای حرکت‌های منتشرشده است و قابل حذف نیست."
        raise SponsorInUseError(msg)

    sponsor.soft_delete()
    logger.info("Madadkar sponsor soft-deleted sponsor_id=%s", sponsor.pk)


# ===========================================================================
# Campaign services
# ===========================================================================

def _validate_campaign_financial_fields(
    *,
    total_amount: int,
    total_shares: int,
) -> None:
    """اعتبارسنجی فیلدهای مالی حرکت."""
    try:
        validate_total_amount(total_amount)
        validate_total_shares(total_shares)
        validate_share_price_divisibility(total_amount, total_shares)
    except DjangoValidationError as exc:
        raise CampaignInvalidDataError(
            _extract_django_validation_message(exc),
        ) from exc


@transaction.atomic
def create_campaign(
    *,
    sponsor: Sponsor,
    title: str,
    description: str,
    cover_image: Any,
    total_amount: int,
    total_shares: int,
    has_deadline: bool = False,
    deadline: Any = None,
    is_visible: bool = False,
) -> Campaign:
    """ساخت یک حرکت جدید در وضعیت DRAFT."""
    _validate_campaign_financial_fields(
        total_amount=total_amount,
        total_shares=total_shares,
    )

    if has_deadline and deadline is None:
        msg = "در صورت فعال بودن مهلت زمانی، تاریخ پایان الزامی است."
        raise CampaignInvalidDataError(msg)

    if not has_deadline and deadline is not None:
        msg = "اگر مهلت زمانی فعال نیست، تاریخ پایان نباید مقداردهی شود."
        raise CampaignInvalidDataError(msg)

    if has_deadline and deadline <= timezone.now():
        msg = "تاریخ پایان باید در آینده باشد."
        raise CampaignInvalidDataError(msg)

    campaign = Campaign(
        sponsor=sponsor,
        title=title,
        description=description,
        cover_image=cover_image,
        total_amount=total_amount,
        total_shares=total_shares,
        has_deadline=has_deadline,
        deadline=deadline,
        is_visible=is_visible,
        status=CampaignStatus.DRAFT,
    )
    campaign.save()

    logger.info(
        "Madadkar campaign created campaign_id=%s sponsor=%s "
        "total_amount=%s total_shares=%s",
        campaign.pk,
        sponsor.pk,
        total_amount,
        total_shares,
    )
    return campaign


_ALWAYS_EDITABLE_FIELDS = {"title", "description", "cover_image", "is_visible"}
_LOCKED_AFTER_FIRST_PAYMENT = {"sponsor", "total_amount", "total_shares"}
_DEADLINE_FIELDS = {"has_deadline", "deadline"}


@transaction.atomic
def update_campaign(*, campaign: Campaign, **fields: Any) -> Campaign:
    """آپدیت فیلدهای حرکت با اعمال قوانین قفل."""
    locked = _has_paid_participations(campaign)
    is_terminal = campaign.status in (
        CampaignStatus.COMPLETED,
        CampaignStatus.CLOSED,
    )

    for field_name in fields:
        if field_name in _ALWAYS_EDITABLE_FIELDS:
            continue

        if is_terminal and field_name not in _ALWAYS_EDITABLE_FIELDS:
            msg = (
                f"حرکت در وضعیت «{campaign.get_status_display()}» قرار دارد و "
                f"فیلد «{field_name}» قابل ویرایش نیست."
            )
            raise CampaignFieldLockedError(msg)

        if locked and field_name in _LOCKED_AFTER_FIRST_PAYMENT:
            msg = (
                f"به دلیل ثبت پرداخت‌های موفق، فیلد «{field_name}» قابل ویرایش نیست."
            )
            raise CampaignFieldLockedError(msg)

    new_total_amount = fields.get("total_amount", campaign.total_amount)
    new_total_shares = fields.get("total_shares", campaign.total_shares)
    if "total_amount" in fields or "total_shares" in fields:
        _validate_campaign_financial_fields(
            total_amount=new_total_amount,
            total_shares=new_total_shares,
        )

    if _DEADLINE_FIELDS & fields.keys():
        new_has_deadline = fields.get("has_deadline", campaign.has_deadline)
        new_deadline = fields.get("deadline", campaign.deadline)

        if new_has_deadline and new_deadline is None:
            msg = "در صورت فعال بودن مهلت زمانی، تاریخ پایان الزامی است."
            raise CampaignInvalidDataError(msg)

        if not new_has_deadline and new_deadline is not None:
            msg = "اگر مهلت زمانی فعال نیست، تاریخ پایان نباید مقداردهی شود."
            raise CampaignInvalidDataError(msg)

        if new_has_deadline and new_deadline <= timezone.now():
            msg = "تاریخ پایان باید در آینده باشد."
            raise CampaignInvalidDataError(msg)

        if (
            locked
            and campaign.has_deadline
            and new_deadline is not None
            and campaign.deadline is not None
            and new_deadline < campaign.deadline
        ):
            msg = (
                "پس از ثبت پرداخت موفق، مهلت پایان فقط می‌تواند به جلو منتقل شود."
            )
            raise CampaignFieldLockedError(msg)

        if locked and campaign.has_deadline and not new_has_deadline:
            msg = "پس از ثبت پرداخت موفق، نمی‌توان مهلت زمانی را غیرفعال کرد."
            raise CampaignFieldLockedError(msg)

    update_fields: list[str] = []
    for field_name, value in fields.items():
        setattr(campaign, field_name, value)
        update_fields.append(field_name)

    if not update_fields:
        return campaign

    update_fields.append("share_price")
    update_fields.append("updated_at")
    campaign.save(update_fields=list(set(update_fields)))

    logger.info(
        "Madadkar campaign updated campaign_id=%s fields=%s",
        campaign.pk,
        list(fields.keys()),
    )
    return campaign


@transaction.atomic
def publish_campaign(*, campaign: Campaign) -> Campaign:
    """انتشار حرکت: DRAFT → PUBLISHED."""
    if campaign.status != CampaignStatus.DRAFT:
        msg = (
            f"فقط حرکت‌های پیش‌نویس قابل انتشار هستند. "
            f"وضعیت فعلی: {campaign.get_status_display()}"
        )
        raise CampaignInvalidStateError(msg)

    campaign.status = CampaignStatus.PUBLISHED
    campaign.published_at = timezone.now()
    campaign.save(update_fields=["status", "published_at", "updated_at"])

    logger.info("Madadkar campaign published campaign_id=%s", campaign.pk)
    return campaign


@transaction.atomic
def close_campaign(*, campaign: Campaign) -> Campaign:
    """بستن دستی حرکت: PUBLISHED → CLOSED."""
    if campaign.status != CampaignStatus.PUBLISHED:
        msg = (
            f"فقط حرکت‌های منتشرشده قابل بستن هستند. "
            f"وضعیت فعلی: {campaign.get_status_display()}"
        )
        raise CampaignInvalidStateError(msg)

    campaign.status = CampaignStatus.CLOSED
    campaign.closed_at = timezone.now()
    campaign.save(update_fields=["status", "closed_at", "updated_at"])

    logger.info("Madadkar campaign closed campaign_id=%s", campaign.pk)
    return campaign


@transaction.atomic
def auto_complete_campaign_if_fully_funded(*, campaign: Campaign) -> Campaign:
    """
    تکمیل خودکار حرکت در صورت پر شدن سهم‌ها.

    داخلی — توسط verify_payment فراخوانی می‌شود.
    """
    if (
        campaign.status == CampaignStatus.PUBLISHED
        and campaign.is_fully_funded
    ):
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = timezone.now()
        campaign.save(update_fields=["status", "completed_at", "updated_at"])
        logger.info(
            "Madadkar campaign auto-completed campaign_id=%s",
            campaign.pk,
        )
    return campaign


@transaction.atomic
def delete_campaign(*, campaign: Campaign) -> None:
    """حذف نرم حرکت — فقط در وضعیت DRAFT مجاز."""
    if campaign.status != CampaignStatus.DRAFT:
        msg = "فقط حرکت‌های پیش‌نویس قابل حذف هستند."
        raise CampaignInvalidStateError(msg)

    campaign.soft_delete()
    logger.info("Madadkar campaign soft-deleted campaign_id=%s", campaign.pk)


# ===========================================================================
# Campaign Image services
# ===========================================================================

@transaction.atomic
def add_campaign_image(
    *,
    campaign: Campaign,
    image: Any,
    alt_text: str = "",
    display_order: int | None = None,
) -> CampaignImage:
    """افزودن یک تصویر به گالری حرکت."""
    if display_order is None:
        last = CampaignImage.objects.filter(
            campaign=campaign,
        ).order_by("-display_order").first()
        display_order = (last.display_order + 1) if last else 0

    gallery_image = CampaignImage.objects.create(
        campaign=campaign,
        image=image,
        alt_text=alt_text,
        display_order=display_order,
    )

    logger.info(
        "Madadkar campaign image added campaign_id=%s image_id=%s",
        campaign.pk,
        gallery_image.pk,
    )
    return gallery_image


@transaction.atomic
def delete_campaign_image(*, image: CampaignImage) -> None:
    """حذف نرم یک تصویر گالری."""
    image.soft_delete()
    logger.info(
        "Madadkar campaign image soft-deleted image_id=%s campaign_id=%s",
        image.pk,
        image.campaign_id,
    )


# ===========================================================================
# Participation services — concurrency-safe share reservation
# ===========================================================================

@transaction.atomic
def initiate_participation(
    *,
    campaign: Campaign,
    user: Any,
    share_count: int,
    callback_url: str,
    ip_address: str | None = None,
    user_agent: str = "",
    mobile: str = "",
    email: str = "",
) -> tuple[Participation, Payment, str]:
    """
    شروع فرآیند مشارکت: رزرو سهم + ساخت Payment + درخواست به درگاه.

    این تابع حیاتی‌ترین قسمت اپ از نظر concurrency است.

    گام‌ها:
    1. اعتبارسنجی share_count
    2. select_for_update روی Campaign (lock کردن row برای جلوگیری از race)
    3. بررسی اینکه حرکت قابل دریافت سهم است (status, deadline, fully_funded)
    4. بررسی اینکه share_count <= remaining_shares
    5. ساخت Participation (PENDING_PAYMENT) — این به‌طور خودکار counter را
       می‌برد بالا چون _sync_campaign_counters فراخوانی می‌شود.
    6. درخواست به provider برای authority + gateway URL
    7. ساخت Payment (PENDING) با authority برگشتی
    8. sync counters
    9. برگشت (participation, payment, gateway_url)

    Args:
        campaign: حرکت مقصد.
        user: کاربر تعیین‌کننده.
        share_count: تعداد سهم (≥ 1).
        callback_url: URL مطلق که درگاه بعد از پرداخت به آن redirect می‌کند.
        ip_address: IP کاربر (برای audit).
        user_agent: User-Agent (برای audit).
        mobile: شماره موبایل (برای provider).
        email: ایمیل (برای provider).

    Returns:
        (participation, payment, gateway_url): سه‌تایی نتیجه.

    Raises:
        InvalidShareCountError: تعداد سهم نامعتبر.
        CampaignNotAcceptingSharesError: حرکت قابل دریافت سهم نیست.
        InsufficientSharesError: سهم درخواستی بیشتر از باقی‌مانده.
        PaymentGatewayError: درگاه پاسخ نامناسب داد.
    """
    try:
        validate_share_count(share_count)
    except DjangoValidationError as exc:
        raise InvalidShareCountError(
            _extract_django_validation_message(exc),
        ) from exc

    # ── lock کردن row کمپین تا انتهای transaction
    locked_campaign = (
        Campaign.objects.select_for_update().get(pk=campaign.pk)
    )

    is_open, reason = _is_campaign_open_for_participation(locked_campaign)
    if not is_open:
        raise CampaignNotAcceptingSharesError(reason)

    if share_count > locked_campaign.remaining_shares:
        msg = (
            f"تعداد سهم درخواستی ({share_count:,}) بیشتر از سهم باقی‌مانده "
            f"({locked_campaign.remaining_shares:,}) است."
        )
        raise InsufficientSharesError(msg)

    # ── ساخت Participation با snapshot قیمت
    share_price_snapshot = locked_campaign.share_price
    total_amount = share_count * share_price_snapshot

    participation = Participation.objects.create(
        campaign=locked_campaign,
        user=user,
        share_count=share_count,
        share_price_snapshot=share_price_snapshot,
        total_amount=total_amount,
        status=ParticipationStatus.PENDING_PAYMENT,
    )

    # ── درخواست به provider
    provider = get_payment_provider()
    description = f"مشارکت در حرکت «{locked_campaign.title}»"

    request_result = provider.request_payment(
        amount=total_amount,
        description=description,
        callback_url=callback_url,
        mobile=mobile,
        email=email,
        metadata={
            "participation_id": str(participation.pk),
            "campaign_id": str(locked_campaign.pk),
            "user_id": str(user.pk),
        },
    )

    if not request_result.success or not request_result.authority:
        logger.warning(
            "Madadkar payment request failed campaign_id=%s user_id=%s "
            "amount=%s error=%s",
            locked_campaign.pk,
            user.pk,
            total_amount,
            request_result.error_message,
        )
        # rollback خودکار با raise شدن exception داخل atomic
        msg = (
            f"ارتباط با درگاه پرداخت برقرار نشد. "
            f"{request_result.error_message or 'لطفاً مجدداً تلاش کنید.'}"
        )
        raise PaymentGatewayError(msg)

    # ── ساخت Payment
    payment = Payment.objects.create(
        participation=participation,
        user=user,
        amount=total_amount,
        gateway_name=provider.name,
        authority=request_result.authority,
        gateway_status=request_result.gateway_status,
        status=PaymentStatus.PENDING,
        ip_address=ip_address,
        user_agent=user_agent[:500] if user_agent else "",
    )
    _record_payment_event(
        payment=payment,
        event_kind=PaymentEventKind.CREATED,
        previous_status="",
        new_status=PaymentStatus.PENDING,
        metadata={"campaign_id": locked_campaign.pk, "participation_id": participation.pk},
    )

    # ── sync counters (PENDING_PAYMENt هم شمارش می‌شود → سهم رزرو می‌ماند)
    _sync_campaign_counters(campaign=locked_campaign)

    logger.info(
        "Madadkar participation initiated participation_id=%s payment_id=%s "
        "campaign_id=%s user_id=%s share_count=%s amount=%s authority=%s",
        participation.pk,
        payment.pk,
        locked_campaign.pk,
        user.pk,
        share_count,
        total_amount,
        payment.authority,
    )

    return participation, payment, request_result.gateway_url


# ===========================================================================
# Payment services — verify + idempotency + anti-tampering
# ===========================================================================

def verify_payment(*, authority: str) -> Payment:
    """
    تأیید پرداخت بر اساس authority برگشتی از درگاه.

    این تابع idempotent است:
    - اگر Payment قبلاً SUCCESS بوده، بدون تماس با درگاه برمی‌گردد.
    - اگر FAILED بوده، بدون تغییر برمی‌گردد.
    - اگر PENDING بوده، با درگاه verify می‌کند.

    معماری transaction:
    این تابع با @transaction.atomic decorate **نشده** است. به جای آن:
    - تماس با provider (slow I/O) خارج از هر atomic block انجام می‌شود.
    - هر بخش mutation در یک atomic block جداگانه با select_for_update
      انجام می‌شود.
    - در سناریوی amount mismatch، تغییرات security در atomic مستقل
      commit می‌شوند، سپس exception raise می‌شود — تا حتی وقتی به caller
      exception می‌دهیم، Payment در DB حتماً FAILED ذخیره شده باشد.

    گام‌ها:
    1. یافتن Payment (بدون lock) — early return در صورت SUCCESS/FAILED.
    2. تماس با provider (خارج از atomic).
    3. amount tampering check — در atomic مستقل save + raise.
    4. ذخیره وضعیت نهایی (SUCCESS یا FAILED) در atomic block با
       select_for_update + double-check idempotency.

    Args:
        authority: کد رهگیری که از callback درگاه دریافت شده.

    Returns:
        Payment آپدیت شده.

    Raises:
        PaymentNotFoundError: payment با این authority یافت نشد.
        PaymentAmountMismatchError: درگاه مبلغ متفاوتی برگرداند (security).
        PaymentGatewayError: خطا در ارتباط با درگاه.
    """
    # ── مرحله ۱: یافتن payment + early-return idempotent
    payment = (
        Payment.objects
        .select_related("participation", "participation__campaign", "user")
        .filter(authority=authority)
        .first()
    )

    if payment is None:
        msg = f"پرداختی با کد رهگیری «{authority}» یافت نشد."
        raise PaymentNotFoundError(msg)

    if payment.status == PaymentStatus.SUCCESS:
        logger.info(
            "Madadkar payment verify idempotent return payment_id=%s authority=%s",
            payment.pk,
            authority,
        )
        return payment

    if payment.status == PaymentStatus.FAILED:
        logger.info(
            "Madadkar payment verify on failed payment payment_id=%s authority=%s",
            payment.pk,
            authority,
        )
        return payment

    # ── مرحله ۲: تماس با provider (خارج از atomic — I/O سنگین)
    provider = get_payment_provider(name=payment.gateway_name)

    try:
        verify_result = provider.verify_payment(
            authority=authority,
            amount=payment.amount,
        )
    except Exception as exc:
        logger.error(
            "Madadkar payment verify gateway error payment_id=%s authority=%s: %s",
            payment.pk,
            authority,
            exc,
            exc_info=True,
        )
        msg = "خطا در ارتباط با درگاه پرداخت. لطفاً بعداً مجدداً تلاش کنید."
        raise PaymentGatewayError(msg) from exc

    now = timezone.now()

    # ── مرحله ۳: anti-tampering check
    # اگر provider success گزارش داد ولی مبلغ تطبیق ندارد → CRITICAL security
    if verify_result.success and verify_result.verified_amount != payment.amount:
        logger.error(
            "Madadkar payment AMOUNT MISMATCH payment_id=%s authority=%s "
            "stored=%s verified=%s",
            payment.pk,
            authority,
            payment.amount,
            verify_result.verified_amount,
        )

        # تغییرات security در یک atomic مستقل commit می‌شوند تا با raise
        # بعدی rollback نشوند. این تضمین می‌کند Payment حتماً FAILED ثبت
        # شود حتی وقتی به caller exception می‌دهیم.
        with transaction.atomic():
            locked_payment = (
                Payment.objects
                .select_for_update()
                .select_related("participation", "participation__campaign")
                .get(pk=payment.pk)
            )
            locked_campaign = (
                Campaign.objects
                .select_for_update()
                .get(pk=locked_payment.participation.campaign_id)
            )
            locked_participation = locked_payment.participation

            previous_status = locked_payment.status
            locked_payment.status = PaymentStatus.FAILED
            locked_payment.gateway_status = verify_result.gateway_status
            locked_payment.verified_at = now
            locked_payment.save(
                update_fields=[
                    "status",
                    "gateway_status",
                    "verified_at",
                    "updated_at",
                ],
            )
            _record_payment_event(
                payment=locked_payment,
                event_kind=PaymentEventKind.AMOUNT_MISMATCH,
                previous_status=previous_status,
                new_status=PaymentStatus.FAILED,
                metadata={
                    "stored_amount": payment.amount,
                    "verified_amount": verify_result.verified_amount,
                },
            )

            locked_participation.status = ParticipationStatus.FAILED
            locked_participation.save(update_fields=["status", "updated_at"])

            _sync_campaign_counters(campaign=locked_campaign)

        msg = (
            "مبلغ تأیید شده توسط درگاه با مبلغ ثبت‌شده مطابقت ندارد. "
            "پرداخت رد شد."
        )
        raise PaymentAmountMismatchError(msg)

    # ── مرحله ۴: ذخیره وضعیت نهایی در atomic block با lock
    with transaction.atomic():
        locked_payment = (
            Payment.objects
            .select_for_update()
            .select_related("participation", "participation__campaign")
            .get(pk=payment.pk)
        )

        # double-check idempotency داخل lock — جلوگیری از race condition
        # که verify دو بار همزمان فراخوانی شده باشد.
        if locked_payment.status in (PaymentStatus.SUCCESS, PaymentStatus.FAILED):
            logger.info(
                "Madadkar payment verify race-detected idempotent return "
                "payment_id=%s status=%s",
                locked_payment.pk,
                locked_payment.status,
            )
            return locked_payment

        locked_campaign = (
            Campaign.objects
            .select_for_update()
            .get(pk=locked_payment.participation.campaign_id)
        )
        locked_participation = locked_payment.participation

        # ── حالت ۱: verify ناموفق → release shares
        if not verify_result.success:
            previous_status = locked_payment.status
            locked_payment.status = PaymentStatus.FAILED
            locked_payment.gateway_status = verify_result.gateway_status
            locked_payment.verified_at = now
            locked_payment.save(
                update_fields=[
                    "status",
                    "gateway_status",
                    "verified_at",
                    "updated_at",
                ],
            )
            _record_payment_event(
                payment=locked_payment,
                event_kind=PaymentEventKind.VERIFY_FAILED,
                previous_status=previous_status,
                new_status=PaymentStatus.FAILED,
                metadata={"error_message": verify_result.error_message},
            )

            locked_participation.status = ParticipationStatus.FAILED
            locked_participation.save(update_fields=["status", "updated_at"])

            _sync_campaign_counters(campaign=locked_campaign)

            logger.warning(
                "Madadkar payment verify failed payment_id=%s authority=%s error=%s",
                locked_payment.pk,
                authority,
                verify_result.error_message,
            )
            return locked_payment

        # ── حالت ۲: verify موفق + amount صحیح → ثبت قطعی
        previous_status = locked_payment.status
        locked_payment.status = PaymentStatus.SUCCESS
        locked_payment.ref_id = verify_result.ref_id
        locked_payment.gateway_status = verify_result.gateway_status
        locked_payment.paid_at = now
        locked_payment.verified_at = now
        locked_payment.save(
            update_fields=[
                "status",
                "ref_id",
                "gateway_status",
                "paid_at",
                "verified_at",
                "updated_at",
            ],
        )
        _record_payment_event(
            payment=locked_payment,
            event_kind=PaymentEventKind.VERIFY_SUCCESS,
            previous_status=previous_status,
            new_status=PaymentStatus.SUCCESS,
            metadata={"already_verified": verify_result.already_verified},
        )

        locked_participation.status = ParticipationStatus.PAID
        locked_participation.paid_at = now
        locked_participation.save(
            update_fields=["status", "paid_at", "updated_at"],
        )

        _sync_campaign_counters(campaign=locked_campaign)
        auto_complete_campaign_if_fully_funded(campaign=locked_campaign)

        logger.info(
            "Madadkar payment verify success payment_id=%s authority=%s "
            "ref_id=%s amount=%s",
            locked_payment.pk,
            authority,
            locked_payment.ref_id,
            locked_payment.amount,
        )
        from apps.notifications.domain import notify_madadkar_payment_success

        notify_madadkar_payment_success(payment=locked_payment)
        return locked_payment


# ===========================================================================
# Maintenance services — Celery taskها از این‌ها استفاده می‌کنند
# ===========================================================================

@transaction.atomic
def expire_stale_participation(*, participation: Participation) -> Participation:
    """
    expire کردن یک Participation راکد (PENDING_PAYMENT خیلی قدیمی).

    این تابع برای استفاده در Celery task طراحی شده.
    سهم رزرو شده آزاد می‌شود.
    """
    if participation.status != ParticipationStatus.PENDING_PAYMENT:
        return participation

    campaign = (
        Campaign.objects
        .select_for_update()
        .get(pk=participation.campaign_id)
    )

    participation.status = ParticipationStatus.EXPIRED
    participation.save(update_fields=["status", "updated_at"])

    # Payment مرتبط را هم FAILED می‌کنیم و ledger event ثبت می‌کنیم.
    payment = Payment.objects.filter(
        participation=participation,
        status=PaymentStatus.PENDING,
    ).first()
    if payment is not None:
        previous_status = payment.status
        payment.status = PaymentStatus.FAILED
        payment.gateway_status = "expired"
        payment.verified_at = timezone.now()
        payment.save(update_fields=["status", "gateway_status", "verified_at", "updated_at"])
        _record_payment_event(
            payment=payment,
            event_kind=PaymentEventKind.EXPIRED,
            previous_status=previous_status,
            new_status=PaymentStatus.FAILED,
        )

    _sync_campaign_counters(campaign=campaign)

    logger.info(
        "Madadkar participation expired participation_id=%s campaign_id=%s",
        participation.pk,
        campaign.pk,
    )
    return participation


def get_stale_participations(*, timeout_minutes: int | None = None) -> Any:
    """
    دریافت queryset از Participationهای PENDING_PAYMENT منقضی شده.

    معیار: created_at قدیمی‌تر از timeout_minutes دقیقه.
    """
    timeout = timeout_minutes or settings.MADADKAR_PAYMENT_TIMEOUT_MINUTES
    cutoff = timezone.now() - timezone.timedelta(minutes=timeout)

    return Participation.objects.filter(
        status=ParticipationStatus.PENDING_PAYMENT,
        created_at__lt=cutoff,
    )


@transaction.atomic
def close_campaign_due_to_deadline(*, campaign: Campaign) -> Campaign:
    """
    بستن خودکار حرکت به دلیل رسیدن deadline.

    برای استفاده در Celery task. تفاوت با close_campaign دستی:
    - این تابع بدون چک wide در حرکت‌های PUBLISHED اعمال می‌شود.
    - اگر در حین rounds قبلی auto-complete شده باشد، تغییری ایجاد نمی‌کند.
    """
    if campaign.status != CampaignStatus.PUBLISHED:
        return campaign

    if not campaign.has_deadline or campaign.deadline is None:
        return campaign

    if campaign.deadline > timezone.now():
        return campaign

    campaign.status = CampaignStatus.CLOSED
    campaign.closed_at = timezone.now()
    campaign.save(update_fields=["status", "closed_at", "updated_at"])

    logger.info(
        "Madadkar campaign auto-closed due to deadline campaign_id=%s",
        campaign.pk,
    )
    return campaign


# ===========================================================================
# Payment reconciliation services
# ===========================================================================

@transaction.atomic
def reconcile_provider_payments(*, provider_name: str, rows: list[dict[str, Any]], source_name: str = "") -> PaymentReconciliationBatch:
    """Reconcile provider settlement/report rows with internal payment ledger.

    Expected row keys are intentionally generic:
    - authority
    - ref_id
    - amount
    - status

    This service performs no external I/O; it compares a provider report snapshot
    with internal Payment records and stores an auditable reconciliation batch.
    """
    batch = PaymentReconciliationBatch.objects.create(
        provider_name=provider_name.strip().lower(),
        source_name=source_name.strip(),
        total_rows=len(rows),
    )
    seen_refs: set[str] = set()
    for row in rows:
        authority = str(row.get("authority") or "").strip()
        ref_id = str(row.get("ref_id") or "").strip()
        provider_status = str(row.get("status") or "").strip().lower()
        provider_amount = int(row.get("amount") or 0)
        duplicate_ref = bool(ref_id and ref_id in seen_refs)
        if ref_id:
            seen_refs.add(ref_id)
        payment = _find_payment_for_reconciliation(provider_name=batch.provider_name, authority=authority, ref_id=ref_id)
        item_status, reason = _classify_reconciliation_row(
            payment=payment,
            provider_amount=provider_amount,
            provider_status=provider_status,
            duplicate_ref=duplicate_ref,
        )
        PaymentReconciliationItem.objects.create(
            batch=batch,
            payment=payment,
            authority=authority,
            provider_ref_id=ref_id,
            provider_amount=provider_amount,
            provider_status=provider_status,
            internal_amount=payment.amount if payment else None,
            internal_status=payment.status if payment else "",
            status=item_status,
            reason=reason,
            raw_payload=row,
        )
    _finalize_reconciliation_batch(batch=batch)
    return batch


def _find_payment_for_reconciliation(*, provider_name: str, authority: str, ref_id: str) -> Payment | None:
    """Find internal payment by authority first, then provider ref_id."""
    queryset = Payment.objects.filter(gateway_name=provider_name)
    if authority:
        payment = queryset.filter(authority=authority).first()
        if payment is not None:
            return payment
    if ref_id:
        return queryset.filter(ref_id=ref_id).first()
    return None


def _classify_reconciliation_row(*, payment: Payment | None, provider_amount: int, provider_status: str, duplicate_ref: bool) -> tuple[str, str]:
    """Classify one provider row compared to internal payment state."""
    if duplicate_ref:
        return ReconciliationItemStatus.DUPLICATE_PROVIDER_REF, "شناسه مرجع در گزارش درگاه تکراری است."
    if payment is None:
        return ReconciliationItemStatus.MISSING_INTERNAL, "پرداخت متناظر در سیستم داخلی پیدا نشد."
    if provider_amount and provider_amount != payment.amount:
        return ReconciliationItemStatus.AMOUNT_MISMATCH, "مبلغ گزارش درگاه با مبلغ داخلی تطابق ندارد."
    provider_success = provider_status in {"success", "paid", "verified", "100", "101"}
    if provider_success and payment.status != PaymentStatus.SUCCESS:
        return ReconciliationItemStatus.STATUS_MISMATCH, "درگاه پرداخت را موفق می‌داند اما وضعیت داخلی موفق نیست."
    if not provider_success and payment.status == PaymentStatus.SUCCESS:
        return ReconciliationItemStatus.STATUS_MISMATCH, "وضعیت داخلی موفق است اما گزارش درگاه موفق نیست."
    return ReconciliationItemStatus.MATCHED, "تطبیق موفق."


def _finalize_reconciliation_batch(*, batch: PaymentReconciliationBatch) -> PaymentReconciliationBatch:
    """Aggregate reconciliation item counters and mark batch completed."""
    items = batch.items.all()
    batch.matched_count = items.filter(status=ReconciliationItemStatus.MATCHED).count()
    batch.missing_internal_count = items.filter(status=ReconciliationItemStatus.MISSING_INTERNAL).count()
    batch.duplicate_provider_ref_count = items.filter(status=ReconciliationItemStatus.DUPLICATE_PROVIDER_REF).count()
    batch.mismatch_count = items.exclude(status=ReconciliationItemStatus.MATCHED).count()
    batch.status = ReconciliationStatus.COMPLETED
    batch.completed_at = timezone.now()
    batch.summary = {
        "matched": batch.matched_count,
        "mismatches": batch.mismatch_count,
        "missing_internal": batch.missing_internal_count,
        "duplicate_provider_ref": batch.duplicate_provider_ref_count,
    }
    batch.save(update_fields=[
        "matched_count",
        "missing_internal_count",
        "duplicate_provider_ref_count",
        "mismatch_count",
        "status",
        "completed_at",
        "summary",
        "updated_at",
    ])
    return batch
