"""
Selectors اپ مددکار — read-only query functions.

این لایه فقط queryهای optimized برای read را شامل می‌شود.
هیچ mutation اینجا انجام نمی‌شود — برای آن از services استفاده شود.

اصول:
- prefetch/select_related برای کاهش N+1.
- scope tagging: public vs admin vs user.
- consistent ordering برای pagination stability.
- user-scoped selectors به‌صورت خودکار IDOR-safe هستند (فیلتر روی user_id).
- analytics selectors برای admin: leaderboard، export، stats.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, QuerySet, Sum
from django.utils import timezone

from apps.madadkar.choices import CampaignStatus, ParticipationStatus
from apps.madadkar.models import (
    Campaign,
    CampaignImage,
    Participation,
    Payment,
    Sponsor,
)

# ---------------------------------------------------------------------------
# Sponsor selectors
# ---------------------------------------------------------------------------

def get_public_sponsors_queryset() -> QuerySet[Sponsor]:
    """
    لیست مددکاران برای نمایش عمومی.

    شامل فقط Sponsorهایی که حداقل یک Campaign قابل نمایش دارند.
    """
    return Sponsor.objects.filter(
        campaigns__is_visible=True,
        campaigns__is_active=True,
        campaigns__status__in=[
            CampaignStatus.PUBLISHED,
            CampaignStatus.COMPLETED,
            CampaignStatus.CLOSED,
        ],
    ).distinct().order_by("name")


def get_admin_sponsors_queryset() -> QuerySet[Sponsor]:
    """لیست کامل مددکاران فعال برای ادمین."""
    return Sponsor.objects.all().order_by("name")


def get_sponsor_by_slug_public(slug: str) -> Sponsor | None:
    """یک مددکار برای نمایش عمومی با slug."""
    return get_public_sponsors_queryset().filter(slug=slug).first()


def get_sponsor_by_id_admin(sponsor_id: int) -> Sponsor | None:
    """یک مددکار برای ادمین با pk."""
    return Sponsor.objects.filter(pk=sponsor_id).first()


# ---------------------------------------------------------------------------
# Campaign selectors — public scope
# ---------------------------------------------------------------------------

def _gallery_prefetch() -> Prefetch:
    """Prefetch گالری حرکت با ordering مشخص."""
    return Prefetch(
        "gallery_images",
        queryset=CampaignImage.objects.filter(is_active=True).order_by(
            "display_order",
            "created_at",
        ),
    )


def get_public_campaigns_queryset() -> QuerySet[Campaign]:
    """
    لیست حرکت‌های قابل نمایش عمومی.

    شامل: is_active=True + is_visible=True + status در [PUBLISHED, COMPLETED, CLOSED].
    """
    return (
        Campaign.visible.select_related("sponsor")
        .prefetch_related(_gallery_prefetch())
        .order_by("-published_at", "-created_at")
    )


def get_public_campaign_by_slug(slug: str) -> Campaign | None:
    """یک حرکت برای نمایش عمومی با slug."""
    return get_public_campaigns_queryset().filter(slug=slug).first()


def get_public_campaigns_by_sponsor(sponsor: Sponsor) -> QuerySet[Campaign]:
    """حرکت‌های قابل نمایش یک مددکار."""
    return get_public_campaigns_queryset().filter(sponsor=sponsor)


# ---------------------------------------------------------------------------
# Campaign selectors — admin scope
# ---------------------------------------------------------------------------

def get_admin_campaigns_queryset() -> QuerySet[Campaign]:
    """لیست کامل حرکت‌ها برای ادمین (همه وضعیت‌ها به جز soft-deleted)."""
    return (
        Campaign.objects.select_related("sponsor")
        .prefetch_related(_gallery_prefetch())
        .order_by("-created_at")
    )


def get_admin_campaign_by_id(campaign_id: int) -> Campaign | None:
    """یک حرکت برای ادمین با pk."""
    return get_admin_campaigns_queryset().filter(pk=campaign_id).first()


# ---------------------------------------------------------------------------
# Campaign selectors — operational
# ---------------------------------------------------------------------------

def get_campaigns_due_for_closing() -> QuerySet[Campaign]:
    """
    حرکت‌هایی که deadline آن‌ها رسیده ولی هنوز PUBLISHED هستند.

    استفاده در Celery task برای بستن خودکار.
    """
    return Campaign.objects.filter(
        is_active=True,
        status=CampaignStatus.PUBLISHED,
        has_deadline=True,
        deadline__lte=timezone.now(),
    )


# ---------------------------------------------------------------------------
# Participation selectors — user scope (IDOR-safe)
# ---------------------------------------------------------------------------

def _participation_user_queryset_base() -> QuerySet[Participation]:
    """
    queryset پایه برای participationهای کاربر.

    eager loadهای استاندارد:
    - campaign + sponsor (برای نمایش خلاصه campaign)
    - payment (one-to-one — برای نمایش وضعیت پرداخت)
    """
    return (
        Participation.objects
        .select_related(
            "campaign",
            "campaign__sponsor",
            "payment",
            "user",
        )
        .order_by("-created_at")
    )


def get_user_participations_queryset(*, user_id: int) -> QuerySet[Participation]:
    """
    لیست مشارکت‌های یک کاربر مشخص.

    IDOR-safe: همیشه روی user_id فیلتر می‌شود.
    """
    return _participation_user_queryset_base().filter(user_id=user_id)


def get_user_participation_by_id(
    *,
    user_id: int,
    participation_id: int,
) -> Participation | None:
    """
    دریافت یک مشارکت کاربر با pk.

    IDOR-safe: فقط اگر مالک participation برابر user_id باشد برمی‌گردد.
    در غیر این صورت None.
    """
    return (
        _participation_user_queryset_base()
        .filter(pk=participation_id, user_id=user_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Participation selectors — admin scope
# ---------------------------------------------------------------------------

def _participation_admin_queryset_base() -> QuerySet[Participation]:
    """queryset پایه برای participationهای ادمین — همه کاربران."""
    return (
        Participation.objects
        .select_related(
            "campaign",
            "campaign__sponsor",
            "payment",
            "user",
        )
        .order_by("-created_at")
    )


def get_admin_participations_queryset() -> QuerySet[Participation]:
    """لیست تمام مشارکت‌ها برای ادمین."""
    return _participation_admin_queryset_base()


def get_admin_participations_by_campaign(
    *,
    campaign_id: int,
) -> QuerySet[Participation]:
    """مشارکت‌های یک حرکت مشخص — برای ادمین."""
    return _participation_admin_queryset_base().filter(campaign_id=campaign_id)


def get_admin_participation_by_id(
    *,
    participation_id: int,
) -> Participation | None:
    """یک مشارکت برای ادمین با pk (بدون قید owner)."""
    return (
        _participation_admin_queryset_base()
        .filter(pk=participation_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Payment selectors — admin scope
# ---------------------------------------------------------------------------

def get_admin_payments_queryset() -> QuerySet[Payment]:
    """لیست تمام پرداخت‌ها برای ادمین."""
    return (
        Payment.objects
        .select_related(
            "participation",
            "participation__campaign",
            "user",
        )
        .order_by("-created_at")
    )


def get_payment_by_authority(*, authority: str) -> Payment | None:
    """
    دریافت یک Payment با authority.

    برای استفاده در callback verify (بدون نیاز به user_id چون درگاه
    session کاربر را در callback ندارد).
    """
    return (
        Payment.objects
        .select_related(
            "participation",
            "participation__campaign",
            "user",
        )
        .filter(authority=authority)
        .first()
    )


def get_admin_payment_by_id(*, payment_id: int) -> Payment | None:
    """یک Payment برای ادمین با pk."""
    return get_admin_payments_queryset().filter(pk=payment_id).first()


# ---------------------------------------------------------------------------
# Analytics selectors — admin only
# ---------------------------------------------------------------------------

def get_campaign_paid_participations_queryset(
    *,
    campaign: Campaign,
) -> QuerySet[Participation]:
    """
    فقط participationهای PAID یک حرکت — برای analytics و export.

    ترتیب: بزرگ‌ترین مبلغ ابتدا، سپس آخرین پرداخت‌ها.
    """
    return (
        Participation.objects
        .select_related("user", "payment", "campaign")
        .filter(
            campaign=campaign,
            status=ParticipationStatus.PAID,
        )
        .order_by("-total_amount", "-paid_at")
    )


def get_campaign_participants_for_export(
    *,
    campaign: Campaign,
) -> QuerySet[Participation]:
    """
    Participationها برای خروجی Excel.

    تفاوت با selector بالا: تضمین eager loading همه فیلدهای مورد نیاز export.
    """
    return get_campaign_paid_participations_queryset(campaign=campaign)


def get_campaign_leaderboard(
    *,
    campaign: Campaign,
    top_n: int = 10,
) -> list[dict]:
    """
    Top contributors یک حرکت — بزرگ‌ترین مشارکت‌کنندگان.

    تجمیع بر اساس user_id:
    - total_shares: مجموع سهم خریداری شده
    - total_amount: مجموع مبلغ پرداخت شده
    - participations_count: تعداد دفعات مشارکت

    Returns:
        list of dicts، sorted by total_amount descending.
        هر dict شامل: user_id, user_email, user_display_name,
                       total_shares, total_amount, participations_count
    """
    aggregations = (
        Participation.objects
        .filter(campaign=campaign, status=ParticipationStatus.PAID)
        .values("user_id")
        .annotate(
            total_shares=Sum("share_count"),
            total_amount=Sum("total_amount"),
            participations_count=Count("id"),
        )
        .order_by("-total_amount")[:top_n]
    )

    # eager load user info
    user_ids = [agg["user_id"] for agg in aggregations]
    if not user_ids:
        return []

    from django.contrib.auth import get_user_model
    User = get_user_model()
    users_map = {
        u.pk: u for u in User.objects.filter(pk__in=user_ids)
    }

    result = []
    for agg in aggregations:
        user = users_map.get(agg["user_id"])
        if user is None:
            continue
        full_name = ""
        if hasattr(user, "get_full_name"):
            full_name = (user.get_full_name() or "").strip()
        result.append({
            "user_id": user.pk,
            "user_email": getattr(user, "email", "") or "",
            "user_display_name": (
                full_name or getattr(user, "email", "") or "—"
            ),
            "total_shares": agg["total_shares"] or 0,
            "total_amount": agg["total_amount"] or 0,
            "participations_count": agg["participations_count"] or 0,
        })

    return result


def get_campaign_analytics(*, campaign: Campaign) -> dict:
    """
    آمار تجمیعی یک حرکت برای دشبورد ادمین.

    Returns:
        dict شامل:
        - total_participations: کل تعداد مشارکت (همه وضعیت‌ها)
        - paid_participations: تعداد مشارکت‌های موفق
        - pending_participations: تعداد در انتظار پرداخت
        - failed_participations: تعداد ناموفق
        - expired_participations: تعداد منقضی شده
        - total_paid_amount: مجموع مبلغ پرداخت‌های موفق
        - total_paid_shares: مجموع سهم پرداخت‌های موفق
        - unique_paid_users: تعداد کاربران یکتای پرداخت‌کننده
        - progress_percent: درصد پیشرفت فروش سهم
        - remaining_shares: سهم باقی‌مانده
    """
    from django.db.models import Q

    counts = (
        Participation.objects
        .filter(campaign=campaign)
        .aggregate(
            total=Count("id"),
            paid=Count("id", filter=Q(status=ParticipationStatus.PAID)),
            pending=Count(
                "id", filter=Q(status=ParticipationStatus.PENDING_PAYMENT),
            ),
            failed=Count("id", filter=Q(status=ParticipationStatus.FAILED)),
            expired=Count("id", filter=Q(status=ParticipationStatus.EXPIRED)),
        )
    )

    paid_aggregates = (
        Participation.objects
        .filter(campaign=campaign, status=ParticipationStatus.PAID)
        .aggregate(
            total_amount=Sum("total_amount"),
            total_shares=Sum("share_count"),
            unique_users=Count("user_id", distinct=True),
        )
    )

    return {
        "total_participations": counts["total"] or 0,
        "paid_participations": counts["paid"] or 0,
        "pending_participations": counts["pending"] or 0,
        "failed_participations": counts["failed"] or 0,
        "expired_participations": counts["expired"] or 0,
        "total_paid_amount": paid_aggregates["total_amount"] or 0,
        "total_paid_shares": paid_aggregates["total_shares"] or 0,
        "unique_paid_users": paid_aggregates["unique_users"] or 0,
        "progress_percent": campaign.progress_percent,
        "remaining_shares": campaign.remaining_shares,
    }
