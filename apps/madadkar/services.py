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
from django.db.models import BigIntegerField, Case, Count, F, Q, Sum, When
from django.utils import timezone

from apps.madadkar.choices import (
    CampaignStatus,
    DisbursementStatus,
    FinancialAdjustmentStatus,
    FinancialAdjustmentType,
    FinancialControlSeverity,
    MadadkarRiskSeverity,
    MadadkarRiskSignalType,
    MadadkarRiskStatus,
    ParticipationStatus,
    PaymentEventKind,
    PaymentStatus,
    ReconciliationItemStatus,
    ReconciliationStatus,
    RefundReason,
    RefundStatus,
)
from apps.madadkar.models import (
    Campaign,
    CampaignDisbursement,
    CampaignFinancialAdjustment,
    CampaignImage,
    DonationReceipt,
    MadadkarFinancialControlSnapshot,
    MadadkarRiskSignal,
    Participation,
    Payment,
    PaymentEvent,
    PaymentReconciliationBatch,
    PaymentReconciliationItem,
    PaymentRefund,
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


class RefundWorkflowError(MadadkarServiceError):
    """خطای workflow بازپرداخت مددکار."""


class FinancialAdjustmentWorkflowError(MadadkarServiceError):
    """خطای workflow اصلاح مالی مددکار."""


class DisbursementWorkflowError(MadadkarServiceError):
    """خطای workflow تخصیص/خروج پول مددکار."""


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
      منهای refundهای COMPLETED به‌علاوهٔ adjustmentهای APPLIED
    - participant_count: COUNT DISTINCT user_id برای PAID

    باید با transaction.atomic فراخوانی شود و در صورت نیاز
    select_for_update روی campaign اعمال شده باشد.

    چرا delta-based نشد
    --------------------
    وسوسه‌کننده است که در مسیر داغ به‌جای بازمحاسبه از ``F("purchased_shares")
    + n`` استفاده شود. این کار عمداً انجام *نشده*: نگهداری delta روی یک
    شمارندهٔ **مالی** یک کلاس کامل از باگ‌های drift را وارد می‌کند (رویداد
    گم‌شده، جبران دوباره‌اعمال‌شده، تسک تکراری) که بی‌صدا انباشته می‌شوند و
    فقط وقتی کشف می‌شوند که عدد نمایش‌داده‌شده به کاربر غلط از آب دربیاید.
    بازمحاسبه از منبع حقیقت خودترمیم است.

    آنچه اصلاح شد، هزینهٔ خود بازمحاسبه است:

    - دو ``aggregate`` جدا روی همان جدول با conditional aggregation در یک
      کوئری ادغام شد.
    - جمع adjustmentها که با یک حلقهٔ پایتونی روی **تمام** ردیف‌ها انجام
      می‌شد به ``Case/When`` سمت دیتابیس منتقل شد. مورد قبلی تنها بخش
      بی‌کران این تابع بود: با رشد تعداد adjustment یک حرکت، هر رویداد
      پرداخت همهٔ آن ردیف‌ها را از دیتابیس می‌کشید و در پایتون جمع می‌زد.

    نتیجه: ۴ کوئری با یک fetch بی‌کران → ۳ کوئری، همگی aggregate و
    index-scoped. ایندکس ``(campaign, status)`` روی Participation این
    بازمحاسبه را به یک range scan محدود به همان حرکت نگه می‌دارد.
    """
    aggregates = campaign.participations.aggregate(
        reserved_shares=Sum(
            "share_count",
            filter=Q(
                status__in=[
                    ParticipationStatus.PAID,
                    ParticipationStatus.PENDING_PAYMENT,
                ],
            ),
        ),
        paid_amount=Sum("total_amount", filter=Q(status=ParticipationStatus.PAID)),
        unique_users=Count("user_id", distinct=True, filter=Q(status=ParticipationStatus.PAID)),
    )

    completed_refunds = (
        PaymentRefund.objects.filter(
            payment__participation__campaign=campaign,
            payment__participation__status=ParticipationStatus.PAID,
            status=RefundStatus.COMPLETED,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    # معادل سمت دیتابیسِ property پایتونی ``signed_amount``: CREDIT مثبت،
    # هر چیز دیگری منفی. علامت‌ها باید با آن property هم‌راستا بمانند.
    adjustment_delta = (
        CampaignFinancialAdjustment.objects.filter(
            campaign=campaign,
            status=FinancialAdjustmentStatus.APPLIED,
        ).aggregate(
            delta=Sum(
                Case(
                    When(adjustment_type=FinancialAdjustmentType.CREDIT, then=F("amount")),
                    default=-F("amount"),
                    output_field=BigIntegerField(),
                ),
            ),
        )["delta"]
        or 0
    )

    campaign.purchased_shares = aggregates["reserved_shares"] or 0
    campaign.purchased_amount = max(
        (aggregates["paid_amount"] or 0) - completed_refunds + adjustment_delta, 0
    )
    campaign.participant_count = aggregates["unique_users"] or 0
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
    active_campaigns_exist = (
        Campaign.objects.filter(
            sponsor=sponsor,
        )
        .exclude(status=CampaignStatus.DRAFT)
        .exists()
    )

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
        "Madadkar campaign created campaign_id=%s sponsor=%s total_amount=%s total_shares=%s",
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
            msg = f"به دلیل ثبت پرداخت‌های موفق، فیلد «{field_name}» قابل ویرایش نیست."
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
            msg = "پس از ثبت پرداخت موفق، مهلت پایان فقط می‌تواند به جلو منتقل شود."
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
        msg = f"فقط حرکت‌های پیش‌نویس قابل انتشار هستند. وضعیت فعلی: {campaign.get_status_display()}"
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
        msg = f"فقط حرکت‌های منتشرشده قابل بستن هستند. وضعیت فعلی: {campaign.get_status_display()}"
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
    if campaign.status == CampaignStatus.PUBLISHED and campaign.is_fully_funded:
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
        last = (
            CampaignImage.objects.filter(
                campaign=campaign,
            )
            .order_by("-display_order")
            .first()
        )
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
def _reserve_participation_shares(
    *,
    campaign: Campaign,
    user: Any,
    share_count: int,
) -> Participation:
    """
    فاز رزرو: قفل کمپین، بررسی موجودی سهم و ساخت Participation در وضعیت انتظار.

    این تابع عمداً کوتاه است. تنها کاری که با قفل ردیف کمپین انجام می‌شود
    خواندن/نوشتن دیتابیس است — هیچ I/O شبکه‌ای در این محدوده وجود ندارد،
    بنابراین قفل در حد چند میلی‌ثانیه نگه داشته می‌شود.
    """
    locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)

    is_open, reason = _is_campaign_open_for_participation(locked_campaign)
    if not is_open:
        raise CampaignNotAcceptingSharesError(reason)

    if share_count > locked_campaign.remaining_shares:
        msg = (
            f"تعداد سهم درخواستی ({share_count:,}) بیشتر از سهم باقی‌مانده "
            f"({locked_campaign.remaining_shares:,}) است."
        )
        raise InsufficientSharesError(msg)

    share_price_snapshot = locked_campaign.share_price
    participation = Participation.objects.create(
        campaign=locked_campaign,
        user=user,
        share_count=share_count,
        share_price_snapshot=share_price_snapshot,
        total_amount=share_count * share_price_snapshot,
        status=ParticipationStatus.PENDING_PAYMENT,
    )

    # PENDING_PAYMENT هم شمرده می‌شود تا سهم رزرو بماند و oversell رخ ندهد.
    _sync_campaign_counters(campaign=locked_campaign)
    return participation


@transaction.atomic
def _release_reserved_participation(*, participation: Participation, reason: str) -> None:
    """
    فاز جبران: آزادسازی سهم رزروشده وقتی درگاه پاسخ موفق نداد.

    رکورد Participation حذف نمی‌شود بلکه به FAILED می‌رود. دلیل: تلاش
    ناموفق پرداخت یک واقعیت کسب‌وکاری است و برای تحلیل تقلب، پشتیبانی و
    گزارش‌های مالی باید ردش بماند. چون FAILED در شمارش رزرو نمی‌آید، سهم
    بلافاصله آزاد می‌شود.
    """
    locked_participation = Participation.objects.select_for_update().get(pk=participation.pk)
    if locked_participation.status != ParticipationStatus.PENDING_PAYMENT:
        return

    locked_campaign = Campaign.objects.select_for_update().get(pk=locked_participation.campaign_id)
    locked_participation.status = ParticipationStatus.FAILED
    locked_participation.save(update_fields=["status", "updated_at"])
    _sync_campaign_counters(campaign=locked_campaign)

    participation.status = ParticipationStatus.FAILED
    logger.warning(
        "Madadkar reserved shares released participation_id=%s campaign_id=%s reason=%s",
        locked_participation.pk,
        locked_participation.campaign_id,
        reason,
    )


@transaction.atomic
def _persist_initiated_payment(
    *,
    participation: Participation,
    user: Any,
    amount: int,
    provider_name: str,
    request_result: Any,
    ip_address: str | None,
    user_agent: str,
) -> Payment:
    """فاز ثبت: ذخیره‌ی Payment و رویداد آن پس از پاسخ موفق درگاه."""
    payment = Payment.objects.create(
        participation=participation,
        user=user,
        amount=amount,
        gateway_name=provider_name,
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
        metadata={
            "campaign_id": participation.campaign_id,
            "participation_id": participation.pk,
        },
    )
    return payment


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
    شروع فرآیند مشارکت: رزرو سهم + درخواست به درگاه + ساخت Payment.

    این تابع حیاتی‌ترین قسمت اپ از نظر concurrency است.

    معماری transaction (سه فاز مجزا):
        این تابع عمداً با @transaction.atomic decorate **نشده** است.
        پیش‌تر کل بدنه در یک atomic بود و فراخوانی HTTP به درگاه (تا ۱۰
        ثانیه timeout) در حالی انجام می‌شد که قفل `select_for_update`
        روی ردیف کمپین نگه داشته شده بود. نتیجه: روی یک کمپین پرترافیک،
        مشارکت‌ها کاملاً سریال می‌شدند و هر کندی درگاه به‌صورت آبشاری
        connectionهای دیتابیس و workerهای gunicorn را مصرف می‌کرد.

        حالا:
          فاز ۱ — رزرو سهم در یک atomic کوتاه با قفل کمپین (بدون I/O).
          فاز ۲ — تماس با درگاه، کاملاً خارج از هر transaction و قفلی.
          فاز ۳ — ثبت Payment در یک atomic کوتاه.
        اگر فاز ۲ شکست بخورد، فاز جبران سهم رزروشده را آزاد می‌کند.

        همین الگو در `verify_payment` از قبل رعایت شده بود؛ این تابع تنها
        جای باقی‌مانده بود که I/O خارجی را زیر قفل نگه می‌داشت.

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
        PaymentGatewayError: درگاه پاسخ نامناسب داد یا در دسترس نبود.
    """
    try:
        validate_share_count(share_count)
    except DjangoValidationError as exc:
        raise InvalidShareCountError(
            _extract_django_validation_message(exc),
        ) from exc

    # ── فاز ۱: رزرو سهم (atomic کوتاه، قفل کمپین، بدون I/O)
    participation = _reserve_participation_shares(
        campaign=campaign,
        user=user,
        share_count=share_count,
    )
    total_amount = participation.total_amount

    # ── فاز ۲: تماس با درگاه — خارج از transaction و بدون هیچ قفلی
    provider = get_payment_provider()
    description = f"مشارکت در حرکت «{campaign.title}»"

    try:
        request_result = provider.request_payment(
            amount=total_amount,
            description=description,
            callback_url=callback_url,
            mobile=mobile,
            email=email,
            metadata={
                "participation_id": str(participation.pk),
                "campaign_id": str(campaign.pk),
                "user_id": str(user.pk),
            },
        )
    except Exception as exc:
        _release_reserved_participation(
            participation=participation,
            reason=f"gateway_exception:{type(exc).__name__}",
        )
        logger.error(
            "Madadkar payment request raised campaign_id=%s user_id=%s amount=%s error=%s",
            campaign.pk,
            user.pk,
            total_amount,
            exc,
            exc_info=True,
        )
        msg = "ارتباط با درگاه پرداخت برقرار نشد. لطفاً مجدداً تلاش کنید."
        raise PaymentGatewayError(msg) from exc

    if not request_result.success or not request_result.authority:
        _release_reserved_participation(
            participation=participation,
            reason="gateway_rejected",
        )
        logger.warning(
            "Madadkar payment request failed campaign_id=%s user_id=%s amount=%s error=%s",
            campaign.pk,
            user.pk,
            total_amount,
            request_result.error_message,
        )
        msg = (
            f"ارتباط با درگاه پرداخت برقرار نشد. "
            f"{request_result.error_message or 'لطفاً مجدداً تلاش کنید.'}"
        )
        raise PaymentGatewayError(msg)

    # ── فاز ۳: ثبت Payment (atomic کوتاه)
    payment = _persist_initiated_payment(
        participation=participation,
        user=user,
        amount=total_amount,
        provider_name=provider.name,
        request_result=request_result,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    logger.info(
        "Madadkar participation initiated participation_id=%s payment_id=%s "
        "campaign_id=%s user_id=%s share_count=%s amount=%s authority=%s",
        participation.pk,
        payment.pk,
        campaign.pk,
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
        Payment.objects.select_related("participation", "participation__campaign", "user")
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
            "Madadkar payment AMOUNT MISMATCH payment_id=%s authority=%s stored=%s verified=%s",
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
                Payment.objects.select_for_update()
                .select_related("participation", "participation__campaign")
                .get(pk=payment.pk)
            )
            locked_campaign = Campaign.objects.select_for_update().get(
                pk=locked_payment.participation.campaign_id
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

        msg = "مبلغ تأیید شده توسط درگاه با مبلغ ثبت‌شده مطابقت ندارد. پرداخت رد شد."
        raise PaymentAmountMismatchError(msg)

    # ── مرحله ۴: ذخیره وضعیت نهایی در atomic block با lock
    with transaction.atomic():
        locked_payment = (
            Payment.objects.select_for_update()
            .select_related("participation", "participation__campaign")
            .get(pk=payment.pk)
        )

        # double-check idempotency داخل lock — جلوگیری از race condition
        # که verify دو بار همزمان فراخوانی شده باشد.
        if locked_payment.status in (PaymentStatus.SUCCESS, PaymentStatus.FAILED):
            logger.info(
                "Madadkar payment verify race-detected idempotent return payment_id=%s status=%s",
                locked_payment.pk,
                locked_payment.status,
            )
            return locked_payment

        locked_campaign = Campaign.objects.select_for_update().get(
            pk=locked_payment.participation.campaign_id
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
            "Madadkar payment verify success payment_id=%s authority=%s ref_id=%s amount=%s",
            locked_payment.pk,
            authority,
            locked_payment.ref_id,
            locked_payment.amount,
        )
        from apps.notifications.domain import notify_madadkar_payment_success

        issue_donation_receipt_for_payment(payment=locked_payment)
        evaluate_payment_risk(payment=locked_payment)
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

    campaign = Campaign.objects.select_for_update().get(pk=participation.campaign_id)

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
# Refund / adjustment workflow services
# ===========================================================================


def _completed_refund_total(*, payment: Payment) -> int:
    """Return already completed refund amount for a payment."""
    return (
        PaymentRefund.objects.filter(payment=payment, status=RefundStatus.COMPLETED).aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )


def _open_refund_total(*, payment: Payment) -> int:
    """Return refund amount already locked by non-terminal refund requests."""
    return (
        PaymentRefund.objects.filter(
            payment=payment,
            status__in=[RefundStatus.PENDING_REVIEW, RefundStatus.APPROVED],
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )


@transaction.atomic
def request_payment_refund(
    *,
    payment: Payment,
    amount: int,
    reason: str = RefundReason.OTHER,
    requested_by: Any = None,
    note: str = "",
    idempotency_key: str | None = None,
) -> PaymentRefund:
    """Create a reviewed refund request for a successful payment."""
    locked_payment = (
        Payment.objects.select_for_update()
        .select_related("participation", "participation__campaign")
        .get(pk=payment.pk)
    )
    if locked_payment.status != PaymentStatus.SUCCESS:
        raise RefundWorkflowError("فقط پرداخت‌های موفق قابل بازپرداخت هستند.")
    if amount <= 0:
        raise RefundWorkflowError("مبلغ بازپرداخت باید بزرگ‌تر از صفر باشد.")
    available = (
        locked_payment.amount
        - _completed_refund_total(payment=locked_payment)
        - _open_refund_total(payment=locked_payment)
    )
    if amount > available:
        raise RefundWorkflowError("مبلغ بازپرداخت از مانده قابل بازپرداخت بیشتر است.")
    if idempotency_key:
        existing = PaymentRefund.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
    refund = PaymentRefund.objects.create(
        payment=locked_payment,
        requested_by=requested_by,
        amount=amount,
        reason=reason,
        note=note,
        idempotency_key=idempotency_key,
        status=RefundStatus.PENDING_REVIEW,
    )
    _record_payment_event(
        payment=locked_payment,
        event_kind=PaymentEventKind.REFUND_REQUESTED,
        previous_status=locked_payment.status,
        new_status=locked_payment.status,
        metadata={"refund_id": refund.pk, "amount": amount, "reason": reason},
    )
    evaluate_refund_risk(refund=refund)
    return refund


@transaction.atomic
def approve_payment_refund(
    *, refund: PaymentRefund, reviewed_by: Any = None, note: str = ""
) -> PaymentRefund:
    """Approve a pending refund request without applying financial effects yet."""
    locked_refund = (
        PaymentRefund.objects.select_for_update().select_related("payment").get(pk=refund.pk)
    )
    if locked_refund.status != RefundStatus.PENDING_REVIEW:
        raise RefundWorkflowError("فقط درخواست‌های در انتظار بررسی قابل تأیید هستند.")
    locked_refund.status = RefundStatus.APPROVED
    locked_refund.reviewed_by = reviewed_by
    locked_refund.reviewed_at = timezone.now()
    if note:
        locked_refund.note = note
    locked_refund.save(update_fields=["status", "reviewed_by", "reviewed_at", "note", "updated_at"])
    _record_payment_event(
        payment=locked_refund.payment,
        event_kind=PaymentEventKind.REFUND_APPROVED,
        previous_status=locked_refund.payment.status,
        new_status=locked_refund.payment.status,
        metadata={"refund_id": locked_refund.pk, "amount": locked_refund.amount},
    )
    return locked_refund


@transaction.atomic
def reject_payment_refund(
    *, refund: PaymentRefund, reviewed_by: Any = None, rejection_reason: str = ""
) -> PaymentRefund:
    """Reject a pending refund request with immutable payment ledger evidence."""
    locked_refund = (
        PaymentRefund.objects.select_for_update().select_related("payment").get(pk=refund.pk)
    )
    if locked_refund.status != RefundStatus.PENDING_REVIEW:
        raise RefundWorkflowError("فقط درخواست‌های در انتظار بررسی قابل رد هستند.")
    locked_refund.status = RefundStatus.REJECTED
    locked_refund.reviewed_by = reviewed_by
    locked_refund.reviewed_at = timezone.now()
    locked_refund.rejection_reason = rejection_reason
    locked_refund.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"]
    )
    _record_payment_event(
        payment=locked_refund.payment,
        event_kind=PaymentEventKind.REFUND_REJECTED,
        previous_status=locked_refund.payment.status,
        new_status=locked_refund.payment.status,
        metadata={"refund_id": locked_refund.pk, "reason": rejection_reason},
    )
    return locked_refund


@transaction.atomic
def complete_payment_refund(*, refund: PaymentRefund, provider_ref_id: str = "") -> PaymentRefund:
    """Mark an approved refund as completed and resync campaign accounting."""
    locked_refund = (
        PaymentRefund.objects.select_for_update()
        .select_related("payment", "payment__participation")
        .get(pk=refund.pk)
    )
    if locked_refund.status != RefundStatus.APPROVED:
        raise RefundWorkflowError("فقط بازپرداخت‌های تأییدشده قابل تکمیل هستند.")
    locked_payment = Payment.objects.select_for_update().get(pk=locked_refund.payment_id)
    campaign = Campaign.objects.select_for_update().get(pk=locked_payment.participation.campaign_id)
    locked_refund.status = RefundStatus.COMPLETED
    locked_refund.provider_ref_id = provider_ref_id
    locked_refund.completed_at = timezone.now()
    locked_refund.save(update_fields=["status", "provider_ref_id", "completed_at", "updated_at"])
    if locked_refund.amount >= locked_payment.amount:
        participation = locked_payment.participation
        participation.status = ParticipationStatus.REFUNDED
        participation.save(update_fields=["status", "updated_at"])
    _record_payment_event(
        payment=locked_payment,
        event_kind=PaymentEventKind.REFUND_COMPLETED,
        previous_status=locked_payment.status,
        new_status=locked_payment.status,
        metadata={
            "refund_id": locked_refund.pk,
            "amount": locked_refund.amount,
            "provider_ref_id": provider_ref_id,
            "full_refund": locked_refund.amount >= locked_payment.amount,
        },
    )
    _sync_campaign_counters(campaign=campaign)
    return locked_refund


@transaction.atomic
def create_financial_adjustment(
    *,
    campaign: Campaign,
    amount: int,
    adjustment_type: str,
    reason: str,
    requested_by: Any = None,
    payment: Payment | None = None,
    note: str = "",
) -> CampaignFinancialAdjustment:
    """Create a two-step manual financial adjustment for campaign accounting."""
    if amount <= 0:
        raise FinancialAdjustmentWorkflowError("مبلغ اصلاح مالی باید بزرگ‌تر از صفر باشد.")
    if adjustment_type not in FinancialAdjustmentType.values:
        raise FinancialAdjustmentWorkflowError("نوع اصلاح مالی نامعتبر است.")
    if payment is not None and payment.participation.campaign_id != campaign.pk:
        raise FinancialAdjustmentWorkflowError("پرداخت انتخاب‌شده متعلق به این حرکت نیست.")
    return CampaignFinancialAdjustment.objects.create(
        campaign=campaign,
        payment=payment,
        requested_by=requested_by,
        amount=amount,
        adjustment_type=adjustment_type,
        reason=reason,
        note=note,
        status=FinancialAdjustmentStatus.PENDING_REVIEW,
    )


@transaction.atomic
def approve_financial_adjustment(
    *, adjustment: CampaignFinancialAdjustment, reviewed_by: Any = None
) -> CampaignFinancialAdjustment:
    """Approve a pending financial adjustment before final application."""
    locked_adjustment = CampaignFinancialAdjustment.objects.select_for_update().get(
        pk=adjustment.pk
    )
    if locked_adjustment.status != FinancialAdjustmentStatus.PENDING_REVIEW:
        raise FinancialAdjustmentWorkflowError("فقط اصلاحات در انتظار بررسی قابل تأیید هستند.")
    locked_adjustment.status = FinancialAdjustmentStatus.APPROVED
    locked_adjustment.reviewed_by = reviewed_by
    locked_adjustment.reviewed_at = timezone.now()
    locked_adjustment.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    return locked_adjustment


@transaction.atomic
def reject_financial_adjustment(
    *,
    adjustment: CampaignFinancialAdjustment,
    reviewed_by: Any = None,
    rejection_reason: str = "",
) -> CampaignFinancialAdjustment:
    """Reject a pending financial adjustment with reviewer evidence."""
    locked_adjustment = CampaignFinancialAdjustment.objects.select_for_update().get(
        pk=adjustment.pk
    )
    if locked_adjustment.status != FinancialAdjustmentStatus.PENDING_REVIEW:
        raise FinancialAdjustmentWorkflowError("فقط اصلاحات در انتظار بررسی قابل رد هستند.")
    locked_adjustment.status = FinancialAdjustmentStatus.REJECTED
    locked_adjustment.reviewed_by = reviewed_by
    locked_adjustment.reviewed_at = timezone.now()
    locked_adjustment.rejection_reason = rejection_reason
    locked_adjustment.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"]
    )
    return locked_adjustment


@transaction.atomic
def apply_financial_adjustment(
    *, adjustment: CampaignFinancialAdjustment
) -> CampaignFinancialAdjustment:
    """Apply an approved financial adjustment and resync campaign counters."""
    # نکتهٔ مهم دربارهٔ select_related:
    # `payment` روی CampaignFinancialAdjustment یک FK *nullable* است
    # (on_delete=SET_NULL). select_related روی یک FK nullable یعنی
    # LEFT OUTER JOIN، و PostgreSQL `FOR UPDATE` را روی سمت nullable یک
    # outer join قبول نمی‌کند (NotSupportedError: FOR UPDATE cannot be
    # applied to the nullable side of an outer join). SQLite این را بی‌صدا
    # نادیده می‌گرفت، ولی production روی PostgreSQL این مسیر را با 500
    # می‌شکست. پس فقط خود ردیف adjustment قفل می‌شود و payment در صورت
    # نیاز جداگانه fetch می‌شود (این‌جا فقط خواندنی است و قفلش لازم نیست).
    locked_adjustment = CampaignFinancialAdjustment.objects.select_for_update().get(
        pk=adjustment.pk
    )
    if locked_adjustment.status != FinancialAdjustmentStatus.APPROVED:
        raise FinancialAdjustmentWorkflowError("فقط اصلاحات تأییدشده قابل اعمال هستند.")
    campaign = Campaign.objects.select_for_update().get(pk=locked_adjustment.campaign_id)
    locked_adjustment.status = FinancialAdjustmentStatus.APPLIED
    locked_adjustment.applied_at = timezone.now()
    locked_adjustment.save(update_fields=["status", "applied_at", "updated_at"])
    if locked_adjustment.payment is not None:
        _record_payment_event(
            payment=locked_adjustment.payment,
            event_kind=PaymentEventKind.ADJUSTMENT_APPLIED,
            previous_status=locked_adjustment.payment.status,
            new_status=locked_adjustment.payment.status,
            metadata={
                "adjustment_id": locked_adjustment.pk,
                "amount": locked_adjustment.amount,
                "type": locked_adjustment.adjustment_type,
            },
        )
    _sync_campaign_counters(campaign=campaign)
    evaluate_adjustment_risk(adjustment=locked_adjustment)
    return locked_adjustment


# ===========================================================================
# Financial operations control services
# ===========================================================================


def generate_financial_control_snapshot(
    *, generated_by_task_id: str = ""
) -> MadadkarFinancialControlSnapshot:
    """Generate a daily finance-ops control snapshot from current operational signals."""
    today = timezone.localdate()
    controls = _build_financial_control_payload()
    flags = _build_financial_control_flags(controls=controls)
    severity = _derive_financial_control_severity(flags=flags)
    return MadadkarFinancialControlSnapshot.objects.create(
        generated_for_date=today,
        severity=severity,
        summary={
            "open_flags": len(flags),
            "critical_flags": len(
                [flag for flag in flags if flag["severity"] == FinancialControlSeverity.CRITICAL]
            ),
            "warning_flags": len(
                [flag for flag in flags if flag["severity"] == FinancialControlSeverity.WARNING]
            ),
        },
        controls=controls,
        flags=flags,
        generated_by_task_id=generated_by_task_id,
    )


def _build_financial_control_payload() -> dict[str, Any]:
    """Build raw finance-ops controls from payments, refunds, risk, and disbursements."""
    pending_timeout = settings.MADADKAR_PAYMENT_TIMEOUT_MINUTES
    stale_cutoff = timezone.now() - timezone.timedelta(minutes=pending_timeout)
    return {
        "pending_payments": Payment.objects.filter(status=PaymentStatus.PENDING).count(),
        "stale_pending_payments": Payment.objects.filter(
            status=PaymentStatus.PENDING, created_at__lt=stale_cutoff
        ).count(),
        "open_risk_signals": MadadkarRiskSignal.objects.filter(
            status=MadadkarRiskStatus.OPEN
        ).count(),
        "high_risk_signals": MadadkarRiskSignal.objects.filter(
            status=MadadkarRiskStatus.OPEN,
            severity__in=[MadadkarRiskSeverity.HIGH, MadadkarRiskSeverity.CRITICAL],
        ).count(),
        "pending_refunds": PaymentRefund.objects.filter(status=RefundStatus.PENDING_REVIEW).count(),
        "approved_refunds": PaymentRefund.objects.filter(status=RefundStatus.APPROVED).count(),
        "requested_disbursements": CampaignDisbursement.objects.filter(
            status=DisbursementStatus.REQUESTED
        ).count(),
        "approved_unpaid_disbursements": CampaignDisbursement.objects.filter(
            status=DisbursementStatus.APPROVED
        ).count(),
        "reconciliation_mismatches": PaymentReconciliationBatch.objects.aggregate(
            total=Sum("mismatch_count")
        )["total"]
        or 0,
    }


def _build_financial_control_flags(*, controls: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn raw controls into actionable finance-ops flags."""
    flag_specs = [
        (
            "stale_pending_payments",
            FinancialControlSeverity.WARNING,
            "پرداخت‌های pending منقضی‌شده نیازمند cleanup هستند.",
        ),
        (
            "high_risk_signals",
            FinancialControlSeverity.CRITICAL,
            "سیگنال‌های ریسک high/critical باز وجود دارد.",
        ),
        (
            "pending_refunds",
            FinancialControlSeverity.WATCH,
            "درخواست‌های refund در انتظار بررسی وجود دارد.",
        ),
        (
            "approved_refunds",
            FinancialControlSeverity.WARNING,
            "refundهای تأییدشده هنوز تکمیل نشده‌اند.",
        ),
        (
            "requested_disbursements",
            FinancialControlSeverity.WATCH,
            "درخواست‌های تخصیص مالی در انتظار تأیید وجود دارد.",
        ),
        (
            "approved_unpaid_disbursements",
            FinancialControlSeverity.WARNING,
            "تخصیص‌های تأییدشده هنوز paid نشده‌اند.",
        ),
        (
            "reconciliation_mismatches",
            FinancialControlSeverity.WARNING,
            "اختلافات reconciliation نیازمند بررسی مالی هستند.",
        ),
    ]
    flags = []
    for key, severity, message in flag_specs:
        count = int(controls.get(key) or 0)
        if count > 0:
            flags.append({"key": key, "severity": severity, "count": count, "message": message})
    return flags


def _derive_financial_control_severity(*, flags: list[dict[str, Any]]) -> str:
    """Derive overall snapshot severity from actionable flags."""
    severities = [flag["severity"] for flag in flags]
    if FinancialControlSeverity.CRITICAL in severities:
        return FinancialControlSeverity.CRITICAL
    if FinancialControlSeverity.WARNING in severities:
        return FinancialControlSeverity.WARNING
    if FinancialControlSeverity.WATCH in severities:
        return FinancialControlSeverity.WATCH
    return FinancialControlSeverity.HEALTHY


# ===========================================================================
# Disbursement / allocation ledger services
# ===========================================================================


def calculate_campaign_disbursable_amount(*, campaign: Campaign) -> int:
    """Return current net amount that is not committed to active disbursements."""
    committed = (
        CampaignDisbursement.objects.filter(
            campaign=campaign,
            status__in=[
                DisbursementStatus.REQUESTED,
                DisbursementStatus.APPROVED,
                DisbursementStatus.PAID,
            ],
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    return max(campaign.purchased_amount - committed, 0)


@transaction.atomic
def request_campaign_disbursement(
    *,
    campaign: Campaign,
    amount: int,
    recipient_name: str,
    purpose: str,
    requested_by: Any = None,
    recipient_identifier: str = "",
    recipient_bank_account: str = "",
    supporting_document: dict[str, Any] | None = None,
    note: str = "",
) -> CampaignDisbursement:
    """Create a requested disbursement while preventing over-allocation."""
    locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    if amount <= 0:
        raise DisbursementWorkflowError("مبلغ تخصیص باید بزرگ‌تر از صفر باشد.")
    available = calculate_campaign_disbursable_amount(campaign=locked_campaign)
    if amount > available:
        raise DisbursementWorkflowError("مبلغ تخصیص از مانده قابل تخصیص حرکت بیشتر است.")
    recipient_snapshot = {
        "name": recipient_name.strip(),
        "identifier": recipient_identifier.strip(),
        "bank_account": recipient_bank_account.strip(),
    }
    return CampaignDisbursement.objects.create(
        campaign=locked_campaign,
        requested_by=requested_by,
        amount=amount,
        recipient_name=recipient_snapshot["name"],
        recipient_identifier=recipient_snapshot["identifier"],
        recipient_bank_account=recipient_snapshot["bank_account"],
        recipient_snapshot=recipient_snapshot,
        purpose=purpose.strip(),
        note=note.strip(),
        supporting_document=supporting_document or {},
        status=DisbursementStatus.REQUESTED,
    )


@transaction.atomic
def approve_campaign_disbursement(
    *, disbursement: CampaignDisbursement, reviewed_by: Any = None
) -> CampaignDisbursement:
    """Approve a requested disbursement after re-checking available funds."""
    locked = (
        CampaignDisbursement.objects.select_for_update()
        .select_related("campaign")
        .get(pk=disbursement.pk)
    )
    if locked.status != DisbursementStatus.REQUESTED:
        raise DisbursementWorkflowError("فقط تخصیص‌های درخواست‌شده قابل تأیید هستند.")
    available = calculate_campaign_disbursable_amount(campaign=locked.campaign) + locked.amount
    if locked.amount > available:
        raise DisbursementWorkflowError("مانده قابل تخصیص برای تأیید این درخواست کافی نیست.")
    locked.status = DisbursementStatus.APPROVED
    locked.reviewed_by = reviewed_by
    locked.approved_at = timezone.now()
    locked.save(update_fields=["status", "reviewed_by", "approved_at", "updated_at"])
    return locked


@transaction.atomic
def reject_campaign_disbursement(
    *,
    disbursement: CampaignDisbursement,
    reviewed_by: Any = None,
    rejection_reason: str = "",
) -> CampaignDisbursement:
    """Reject a requested disbursement and release its committed amount."""
    locked = CampaignDisbursement.objects.select_for_update().get(pk=disbursement.pk)
    if locked.status != DisbursementStatus.REQUESTED:
        raise DisbursementWorkflowError("فقط تخصیص‌های درخواست‌شده قابل رد هستند.")
    locked.status = DisbursementStatus.REJECTED
    locked.reviewed_by = reviewed_by
    locked.rejection_reason = rejection_reason.strip()
    locked.rejected_at = timezone.now()
    locked.save(
        update_fields=["status", "reviewed_by", "rejection_reason", "rejected_at", "updated_at"]
    )
    return locked


@transaction.atomic
def mark_campaign_disbursement_paid(
    *,
    disbursement: CampaignDisbursement,
    paid_by: Any = None,
    bank_tracking_reference: str,
) -> CampaignDisbursement:
    """Mark an approved disbursement as paid with bank tracking reference."""
    locked = CampaignDisbursement.objects.select_for_update().get(pk=disbursement.pk)
    if locked.status != DisbursementStatus.APPROVED:
        raise DisbursementWorkflowError("فقط تخصیص‌های تأییدشده قابل پرداخت هستند.")
    if not bank_tracking_reference.strip():
        raise DisbursementWorkflowError("شناسه پیگیری بانکی برای ثبت پرداخت الزامی است.")
    locked.status = DisbursementStatus.PAID
    locked.paid_by = paid_by
    locked.bank_tracking_reference = bank_tracking_reference.strip()
    locked.paid_at = timezone.now()
    locked.save(
        update_fields=["status", "paid_by", "bank_tracking_reference", "paid_at", "updated_at"]
    )
    return locked


# ===========================================================================
# Donation receipt services
# ===========================================================================


def issue_donation_receipt_for_payment(*, payment: Payment) -> DonationReceipt:
    """Issue an idempotent verifiable receipt for a successful payment."""
    if payment.status != PaymentStatus.SUCCESS:
        raise MadadkarServiceError("رسید فقط برای پرداخت موفق صادر می‌شود.")
    existing = DonationReceipt.objects.filter(payment=payment).first()
    if existing is not None:
        return existing
    campaign = payment.participation.campaign
    user = payment.user
    issued_at = payment.paid_at or payment.verified_at or timezone.now()
    receipt = DonationReceipt(
        payment=payment,
        user=user,
        campaign=campaign,
        receipt_number=_build_receipt_number(payment=payment, issued_at=issued_at),
        amount=payment.amount,
        issued_at=issued_at,
        payment_snapshot={
            "payment_id": payment.pk,
            "authority": payment.authority,
            "ref_id": payment.ref_id,
            "gateway_name": payment.gateway_name,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
            "share_count": payment.participation.share_count,
        },
        campaign_snapshot={
            "campaign_id": campaign.pk,
            "title": campaign.title,
            "slug": campaign.slug,
            "sponsor_id": campaign.sponsor_id,
            "sponsor_name": campaign.sponsor.name,
        },
        donor_snapshot={
            "user_id": user.pk,
            "email": getattr(user, "email", "") or "",
            "full_name": user.get_full_name() if hasattr(user, "get_full_name") else "",
        },
    )
    receipt.receipt_hash = receipt.compute_receipt_hash()
    receipt.save()
    return receipt


def _build_receipt_number(*, payment: Payment, issued_at) -> str:
    """Build a stable human-friendly receipt number from payment identity."""
    date_part = issued_at.strftime("%Y%m%d")
    return f"MDK-{date_part}-{payment.pk:010d}"


def verify_donation_receipt(
    *, receipt_number: str, receipt_hash: str
) -> tuple[bool, DonationReceipt | None]:
    """Verify a public receipt number/hash pair without exposing private data."""
    receipt = (
        DonationReceipt.objects.select_related("campaign", "payment", "user")
        .filter(receipt_number=receipt_number)
        .first()
    )
    if receipt is None:
        return False, None
    expected = receipt.compute_receipt_hash()
    return expected == receipt_hash and receipt.receipt_hash == receipt_hash, receipt


@transaction.atomic
def record_receipt_resend(*, receipt: DonationReceipt) -> DonationReceipt:
    """Record an admin/user resend action without mutating forensic receipt payload."""
    locked = DonationReceipt.objects.select_for_update().get(pk=receipt.pk)
    locked.resend_count += 1
    locked.last_resent_at = timezone.now()
    locked.save(update_fields=["resend_count", "last_resent_at", "updated_at"])
    return locked


# ===========================================================================
# Risk scoring services
# ===========================================================================


def create_madadkar_risk_signal(
    *,
    signal_type: str,
    severity: str,
    user: Any | None = None,
    campaign: Campaign | None = None,
    payment: Payment | None = None,
    refund: PaymentRefund | None = None,
    adjustment: CampaignFinancialAdjustment | None = None,
    ip_address: str | None = None,
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> MadadkarRiskSignal:
    """Create an open Madadkar risk signal unless an equivalent open one exists."""
    lookup = {
        "signal_type": signal_type,
        "status": MadadkarRiskStatus.OPEN,
        "user": user if getattr(user, "pk", None) else None,
        "campaign": campaign,
        "payment": payment,
        "refund": refund,
        "adjustment": adjustment,
    }
    existing = MadadkarRiskSignal.objects.filter(**lookup).first()
    if existing is not None:
        return existing
    return MadadkarRiskSignal.objects.create(
        **lookup,
        severity=severity,
        ip_address=ip_address,
        description=description,
        metadata=metadata or {},
    )


def evaluate_payment_risk(
    *, payment: Payment, window_minutes: int = 60
) -> list[MadadkarRiskSignal]:
    """Evaluate payment-level fraud/abuse signals for a payment event."""
    signals: list[MadadkarRiskSignal] = []
    campaign = payment.participation.campaign
    previous_success_count = Payment.objects.filter(
        user_id=payment.user_id,
        status=PaymentStatus.SUCCESS,
        created_at__lt=payment.created_at,
    ).count()
    high_amount_threshold = int(
        getattr(settings, "MADADKAR_RISK_HIGH_AMOUNT_NEW_USER_THRESHOLD", 50_000_000)
    )
    if payment.amount >= high_amount_threshold and previous_success_count == 0:
        signals.append(
            create_madadkar_risk_signal(
                signal_type=MadadkarRiskSignalType.HIGH_AMOUNT_NEW_USER,
                severity=MadadkarRiskSeverity.HIGH,
                user=payment.user,
                campaign=campaign,
                payment=payment,
                ip_address=payment.ip_address,
                description="کاربر بدون سابقه پرداخت موفق، مشارکت مبلغ بالا ثبت کرده است.",
                metadata={"threshold": high_amount_threshold, "amount": payment.amount},
            )
        )
    since = timezone.now() - timezone.timedelta(minutes=window_minutes)
    failure_count = Payment.objects.filter(
        user_id=payment.user_id, status=PaymentStatus.FAILED, created_at__gte=since
    ).count()
    failure_threshold = int(getattr(settings, "MADADKAR_RISK_PAYMENT_FAILURE_SPIKE_THRESHOLD", 3))
    if failure_count >= failure_threshold:
        signals.append(
            create_madadkar_risk_signal(
                signal_type=MadadkarRiskSignalType.PAYMENT_FAILURE_SPIKE,
                severity=MadadkarRiskSeverity.MEDIUM
                if failure_count < failure_threshold * 2
                else MadadkarRiskSeverity.HIGH,
                user=payment.user,
                campaign=campaign,
                payment=payment,
                ip_address=payment.ip_address,
                description="تعداد شکست پرداخت کاربر در بازه کوتاه غیرعادی است.",
                metadata={"window_minutes": window_minutes, "failure_count": failure_count},
            )
        )
    ip_user_threshold = int(getattr(settings, "MADADKAR_RISK_IP_DISTINCT_USERS_THRESHOLD", 3))
    if payment.ip_address:
        distinct_users = (
            Payment.objects.filter(
                ip_address=payment.ip_address,
                created_at__gte=since,
            )
            .values("user_id")
            .distinct()
            .count()
        )
        if distinct_users >= ip_user_threshold:
            signals.append(
                create_madadkar_risk_signal(
                    signal_type=MadadkarRiskSignalType.SUSPICIOUS_IP_VELOCITY,
                    severity=MadadkarRiskSeverity.HIGH,
                    user=payment.user,
                    campaign=campaign,
                    payment=payment,
                    ip_address=payment.ip_address,
                    description="از یک IP در بازه کوتاه برای چند کاربر پرداخت ثبت شده است.",
                    metadata={"window_minutes": window_minutes, "distinct_users": distinct_users},
                )
            )
    return signals


def evaluate_refund_risk(
    *, refund: PaymentRefund, window_hours: int = 24
) -> list[MadadkarRiskSignal]:
    """Evaluate refund velocity and campaign refund spike signals."""
    signals: list[MadadkarRiskSignal] = []
    payment = refund.payment
    campaign = payment.participation.campaign
    since = timezone.now() - timezone.timedelta(hours=window_hours)
    refund_threshold = int(getattr(settings, "MADADKAR_RISK_REFUND_VELOCITY_THRESHOLD", 3))
    user_refunds = PaymentRefund.objects.filter(
        payment__user_id=payment.user_id, created_at__gte=since
    ).count()
    if user_refunds >= refund_threshold:
        signals.append(
            create_madadkar_risk_signal(
                signal_type=MadadkarRiskSignalType.REFUND_VELOCITY,
                severity=MadadkarRiskSeverity.HIGH,
                user=payment.user,
                campaign=campaign,
                payment=payment,
                refund=refund,
                ip_address=payment.ip_address,
                description="تعداد درخواست‌های بازپرداخت کاربر در بازه کوتاه غیرعادی است.",
                metadata={"window_hours": window_hours, "user_refund_count": user_refunds},
            )
        )
    campaign_refunds = PaymentRefund.objects.filter(
        payment__participation__campaign=campaign, created_at__gte=since
    ).count()
    campaign_threshold = int(getattr(settings, "MADADKAR_RISK_CAMPAIGN_REFUND_SPIKE_THRESHOLD", 5))
    if campaign_refunds >= campaign_threshold:
        signals.append(
            create_madadkar_risk_signal(
                signal_type=MadadkarRiskSignalType.CAMPAIGN_REFUND_SPIKE,
                severity=MadadkarRiskSeverity.CRITICAL
                if campaign_refunds >= campaign_threshold * 2
                else MadadkarRiskSeverity.HIGH,
                user=payment.user,
                campaign=campaign,
                payment=payment,
                refund=refund,
                ip_address=payment.ip_address,
                description="در یک حرکت تعداد درخواست بازپرداخت غیرعادی ثبت شده است.",
                metadata={"window_hours": window_hours, "campaign_refund_count": campaign_refunds},
            )
        )
    return signals


def evaluate_adjustment_risk(
    *, adjustment: CampaignFinancialAdjustment
) -> list[MadadkarRiskSignal]:
    """Evaluate unusually large manual financial adjustments."""
    campaign = adjustment.campaign
    ratio_threshold = float(getattr(settings, "MADADKAR_RISK_ADJUSTMENT_RATIO_THRESHOLD", 0.25))
    base_amount = max(campaign.purchased_amount, 1)
    ratio = adjustment.amount / base_amount
    if ratio < ratio_threshold:
        return []
    return [
        create_madadkar_risk_signal(
            signal_type=MadadkarRiskSignalType.ADJUSTMENT_ANOMALY,
            severity=MadadkarRiskSeverity.HIGH if ratio < 0.5 else MadadkarRiskSeverity.CRITICAL,
            user=adjustment.requested_by,
            campaign=campaign,
            payment=adjustment.payment,
            adjustment=adjustment,
            description="مبلغ اصلاح مالی نسبت به مبلغ مؤثر حرکت غیرعادی است.",
            metadata={
                "ratio": round(ratio, 4),
                "amount": adjustment.amount,
                "base_amount": base_amount,
            },
        )
    ]


@transaction.atomic
def review_madadkar_risk_signal(
    *,
    signal: MadadkarRiskSignal,
    reviewed_by: Any,
    status: str,
    review_note: str = "",
) -> MadadkarRiskSignal:
    """Review, dismiss, or escalate an open Madadkar risk signal."""
    if status not in {
        MadadkarRiskStatus.REVIEWED,
        MadadkarRiskStatus.DISMISSED,
        MadadkarRiskStatus.ESCALATED,
    }:
        raise MadadkarServiceError("وضعیت بررسی ریسک نامعتبر است.")
    locked_signal = MadadkarRiskSignal.objects.select_for_update().get(pk=signal.pk)
    locked_signal.status = status
    locked_signal.reviewed_by = reviewed_by
    locked_signal.reviewed_at = timezone.now()
    locked_signal.review_note = review_note
    locked_signal.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
    )
    return locked_signal


# ===========================================================================
# Payment reconciliation services
# ===========================================================================


@transaction.atomic
def reconcile_provider_payments(
    *, provider_name: str, rows: list[dict[str, Any]], source_name: str = ""
) -> PaymentReconciliationBatch:
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
        payment = _find_payment_for_reconciliation(
            provider_name=batch.provider_name, authority=authority, ref_id=ref_id
        )
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


def _find_payment_for_reconciliation(
    *, provider_name: str, authority: str, ref_id: str
) -> Payment | None:
    """Find internal payment by authority first, then provider ref_id."""
    queryset = Payment.objects.filter(gateway_name=provider_name)
    if authority:
        payment = queryset.filter(authority=authority).first()
        if payment is not None:
            return payment
    if ref_id:
        return queryset.filter(ref_id=ref_id).first()
    return None


def _classify_reconciliation_row(
    *, payment: Payment | None, provider_amount: int, provider_status: str, duplicate_ref: bool
) -> tuple[str, str]:
    """Classify one provider row compared to internal payment state."""
    if duplicate_ref:
        return (
            ReconciliationItemStatus.DUPLICATE_PROVIDER_REF,
            "شناسه مرجع در گزارش درگاه تکراری است.",
        )
    if payment is None:
        return ReconciliationItemStatus.MISSING_INTERNAL, "پرداخت متناظر در سیستم داخلی پیدا نشد."
    if provider_amount and provider_amount != payment.amount:
        return (
            ReconciliationItemStatus.AMOUNT_MISMATCH,
            "مبلغ گزارش درگاه با مبلغ داخلی تطابق ندارد.",
        )
    provider_success = provider_status in {"success", "paid", "verified", "100", "101"}
    if provider_success and payment.status != PaymentStatus.SUCCESS:
        return (
            ReconciliationItemStatus.STATUS_MISMATCH,
            "درگاه پرداخت را موفق می‌داند اما وضعیت داخلی موفق نیست.",
        )
    if not provider_success and payment.status == PaymentStatus.SUCCESS:
        return (
            ReconciliationItemStatus.STATUS_MISMATCH,
            "وضعیت داخلی موفق است اما گزارش درگاه موفق نیست.",
        )
    return ReconciliationItemStatus.MATCHED, "تطبیق موفق."


def _finalize_reconciliation_batch(
    *, batch: PaymentReconciliationBatch
) -> PaymentReconciliationBatch:
    """Aggregate reconciliation item counters and mark batch completed."""
    items = batch.items.all()
    batch.matched_count = items.filter(status=ReconciliationItemStatus.MATCHED).count()
    batch.missing_internal_count = items.filter(
        status=ReconciliationItemStatus.MISSING_INTERNAL
    ).count()
    batch.duplicate_provider_ref_count = items.filter(
        status=ReconciliationItemStatus.DUPLICATE_PROVIDER_REF
    ).count()
    batch.mismatch_count = items.exclude(status=ReconciliationItemStatus.MATCHED).count()
    batch.status = ReconciliationStatus.COMPLETED
    batch.completed_at = timezone.now()
    batch.summary = {
        "matched": batch.matched_count,
        "mismatches": batch.mismatch_count,
        "missing_internal": batch.missing_internal_count,
        "duplicate_provider_ref": batch.duplicate_provider_ref_count,
    }
    batch.save(
        update_fields=[
            "matched_count",
            "missing_internal_count",
            "duplicate_provider_ref_count",
            "mismatch_count",
            "status",
            "completed_at",
            "summary",
            "updated_at",
        ]
    )
    return batch
