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

from apps.madadkar.choices import (
    CampaignStatus,
    DisbursementStatus,
    FinancialAdjustmentStatus,
    MadadkarRiskStatus,
    ParticipationStatus,
    PaymentStatus,
    RefundStatus,
)
from apps.madadkar.models import (
    Campaign,
    CampaignDisbursement,
    CampaignFinancialAdjustment,
    CampaignImage,
    DonationReceipt,
    MadadkarRiskSignal,
    Participation,
    Payment,
    PaymentReconciliationBatch,
    PaymentReconciliationItem,
    PaymentRefund,
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


# ---------------------------------------------------------------------------
# Refund / adjustment selectors — admin scope
# ---------------------------------------------------------------------------

def get_admin_refunds_queryset() -> QuerySet[PaymentRefund]:
    """Return all refund workflow rows with payment/campaign/user eager loading."""
    return (
        PaymentRefund.objects
        .select_related(
            "payment",
            "payment__participation",
            "payment__participation__campaign",
            "requested_by",
            "reviewed_by",
        )
        .order_by("-created_at")
    )


def get_admin_refund_by_id(*, refund_id: int) -> PaymentRefund | None:
    """Return one refund workflow row for admin review."""
    return get_admin_refunds_queryset().filter(pk=refund_id).first()


def get_admin_adjustments_queryset() -> QuerySet[CampaignFinancialAdjustment]:
    """Return all financial adjustments with campaign/payment/user eager loading."""
    return (
        CampaignFinancialAdjustment.objects
        .select_related("campaign", "payment", "requested_by", "reviewed_by")
        .order_by("-created_at")
    )


def get_admin_adjustment_by_id(*, adjustment_id: int) -> CampaignFinancialAdjustment | None:
    """Return one financial adjustment for admin review."""
    return get_admin_adjustments_queryset().filter(pk=adjustment_id).first()


def get_campaign_financial_control_summary(*, campaign: Campaign) -> dict:
    """Build a campaign accounting-control summary including refunds and adjustments."""
    completed_refunds = PaymentRefund.objects.filter(
        payment__participation__campaign=campaign,
        status="completed",
    ).aggregate(total=Sum("amount"), count=Count("id"))
    applied_adjustments = CampaignFinancialAdjustment.objects.filter(
        campaign=campaign,
        status="applied",
    )
    adjustment_delta = sum(adjustment.signed_amount for adjustment in applied_adjustments)
    return {
        "campaign_id": campaign.pk,
        "gross_paid_amount": Participation.objects.filter(
            campaign=campaign,
            status=ParticipationStatus.PAID,
        ).aggregate(total=Sum("total_amount"))["total"] or 0,
        "completed_refund_amount": completed_refunds["total"] or 0,
        "completed_refund_count": completed_refunds["count"] or 0,
        "applied_adjustment_delta": adjustment_delta,
        "applied_adjustment_count": applied_adjustments.count(),
        "net_effective_amount": campaign.purchased_amount,
        "remaining_shares": campaign.remaining_shares,
    }


# ---------------------------------------------------------------------------
# Risk selectors — admin scope
# ---------------------------------------------------------------------------

def get_admin_risk_signals_queryset() -> QuerySet[MadadkarRiskSignal]:
    """Return all Madadkar risk signals for admin review with eager loading."""
    return (
        MadadkarRiskSignal.objects
        .select_related("user", "campaign", "payment", "refund", "adjustment", "reviewed_by")
        .order_by("-created_at")
    )


def get_admin_risk_signal_by_id(*, signal_id: int) -> MadadkarRiskSignal | None:
    """Return one Madadkar risk signal for admin review."""
    return get_admin_risk_signals_queryset().filter(pk=signal_id).first()


# ---------------------------------------------------------------------------
# Campaign Intelligence selectors — admin scope
# ---------------------------------------------------------------------------

def get_campaign_intelligence(*, campaign: Campaign, days: int = 30) -> dict:
    """Build refund-adjusted intelligence metrics for one campaign."""
    safe_days = max(1, min(days, 365))
    today = timezone.localdate()
    start_date = today - timezone.timedelta(days=safe_days - 1)
    payments = Payment.objects.filter(participation__campaign=campaign)
    successful_payments = payments.filter(status=PaymentStatus.SUCCESS)
    refunds = PaymentRefund.objects.filter(payment__participation__campaign=campaign, status=RefundStatus.COMPLETED)
    adjustments = CampaignFinancialAdjustment.objects.filter(campaign=campaign, status=FinancialAdjustmentStatus.APPLIED)
    trend = _build_campaign_daily_trend(
        successful_payments=successful_payments,
        refunds=refunds,
        adjustments=adjustments,
        start_date=start_date,
        today=today,
    )
    gross_amount = successful_payments.aggregate(total=Sum("amount"))["total"] or 0
    refund_amount = refunds.aggregate(total=Sum("amount"))["total"] or 0
    adjustment_delta = sum(adjustment.signed_amount for adjustment in adjustments)
    net_amount = max(gross_amount - refund_amount + adjustment_delta, 0)
    total_attempts = payments.count()
    success_count = successful_payments.count()
    failed_count = payments.filter(status=PaymentStatus.FAILED).count()
    pending_count = payments.filter(status=PaymentStatus.PENDING).count()
    paid_users = successful_payments.values("user_id").distinct().count()
    donor_concentration = _calculate_donor_concentration(successful_payments=successful_payments, gross_amount=gross_amount)
    velocity = _calculate_campaign_velocity(campaign=campaign, net_amount=net_amount, trend=trend, today=today)
    risk = _calculate_campaign_intelligence_risk(campaign=campaign)
    health_score, health_flags = _calculate_campaign_health_score(
        campaign=campaign,
        success_count=success_count,
        failed_count=failed_count,
        pending_count=pending_count,
        refund_amount=refund_amount,
        gross_amount=gross_amount,
        donor_concentration=donor_concentration,
        open_risk_signals=risk["open_risk_signals"],
        velocity=velocity,
    )
    return {
        "campaign_id": campaign.pk,
        "campaign_title": campaign.title,
        "generated_at": timezone.now().isoformat(),
        "window_days": safe_days,
        "financials": {
            "gross_amount": gross_amount,
            "completed_refund_amount": refund_amount,
            "applied_adjustment_delta": adjustment_delta,
            "net_amount": net_amount,
            "target_amount": campaign.total_amount,
            "remaining_amount": max(campaign.total_amount - net_amount, 0),
            "net_progress_percent": round((net_amount / campaign.total_amount) * 100, 2) if campaign.total_amount else 0,
        },
        "funnel": {
            "payment_attempts": total_attempts,
            "successful_payments": success_count,
            "failed_payments": failed_count,
            "pending_payments": pending_count,
            "success_rate": round((success_count / total_attempts) * 100, 2) if total_attempts else 0,
            "failure_rate": round((failed_count / total_attempts) * 100, 2) if total_attempts else 0,
            "unique_paid_users": paid_users,
        },
        "velocity": velocity,
        "donor_concentration": donor_concentration,
        "risk": risk,
        "health": {"score": health_score, "flags": health_flags},
        "daily_trend": trend,
    }


def get_madadkar_intelligence_overview(*, days: int = 30) -> dict:
    """Build portfolio-level Madadkar intelligence overview for admins."""
    safe_days = max(1, min(days, 365))
    campaigns = Campaign.objects.filter(is_active=True)
    published_campaigns = campaigns.filter(status=CampaignStatus.PUBLISHED)
    campaign_snapshots = [get_campaign_intelligence(campaign=campaign, days=safe_days) for campaign in published_campaigns.order_by("-published_at", "-created_at")[:25]]
    weakest = sorted(campaign_snapshots, key=lambda item: item["health"]["score"])[:5]
    strongest = sorted(campaign_snapshots, key=lambda item: item["health"]["score"], reverse=True)[:5]
    return {
        "generated_at": timezone.now().isoformat(),
        "window_days": safe_days,
        "portfolio": {
            "active_campaigns": campaigns.count(),
            "published_campaigns": published_campaigns.count(),
            "completed_campaigns": campaigns.filter(status=CampaignStatus.COMPLETED).count(),
            "total_open_risk_signals": MadadkarRiskSignal.objects.filter(status=MadadkarRiskStatus.OPEN).count(),
            "total_net_amount": sum(item["financials"]["net_amount"] for item in campaign_snapshots),
            "average_health_score": round(sum(item["health"]["score"] for item in campaign_snapshots) / len(campaign_snapshots), 2) if campaign_snapshots else 0,
        },
        "weakest_campaigns": _summarize_campaign_snapshots(weakest),
        "strongest_campaigns": _summarize_campaign_snapshots(strongest),
    }


def _build_campaign_daily_trend(
    *,
    successful_payments: QuerySet[Payment],
    refunds: QuerySet[PaymentRefund],
    adjustments: QuerySet[CampaignFinancialAdjustment],
    start_date,
    today,
) -> list[dict]:
    """Build a deterministic daily gross/refund/adjustment/net trend."""
    buckets = {
        start_date + timezone.timedelta(days=offset): {
            "date": (start_date + timezone.timedelta(days=offset)).isoformat(),
            "gross_amount": 0,
            "refund_amount": 0,
            "adjustment_delta": 0,
            "net_amount": 0,
            "successful_payments": 0,
        }
        for offset in range((today - start_date).days + 1)
    }
    for payment in successful_payments.filter(created_at__date__gte=start_date, created_at__date__lte=today):
        bucket = buckets[payment.created_at.date()]
        bucket["gross_amount"] += payment.amount
        bucket["successful_payments"] += 1
    for refund in refunds.filter(completed_at__date__gte=start_date, completed_at__date__lte=today):
        completed_at = refund.completed_at or refund.updated_at
        buckets[completed_at.date()]["refund_amount"] += refund.amount
    for adjustment in adjustments.filter(applied_at__date__gte=start_date, applied_at__date__lte=today):
        applied_at = adjustment.applied_at or adjustment.updated_at
        buckets[applied_at.date()]["adjustment_delta"] += adjustment.signed_amount
    for bucket in buckets.values():
        bucket["net_amount"] = max(bucket["gross_amount"] - bucket["refund_amount"] + bucket["adjustment_delta"], 0)
    return list(buckets.values())


def _calculate_donor_concentration(*, successful_payments: QuerySet[Payment], gross_amount: int) -> dict:
    """Calculate donor concentration and top donor dependency risk."""
    top = successful_payments.values("user_id").annotate(total=Sum("amount"), payments=Count("id")).order_by("-total").first()
    top_amount = top["total"] if top else 0
    top_share = round((top_amount / gross_amount) * 100, 2) if gross_amount else 0
    return {
        "top_donor_user_id": top["user_id"] if top else None,
        "top_donor_amount": top_amount,
        "top_donor_share_percent": top_share,
        "is_concentrated": top_share >= 50,
    }


def _calculate_campaign_velocity(*, campaign: Campaign, net_amount: int, trend: list[dict], today) -> dict:
    """Calculate completion velocity and estimated completion date."""
    non_zero_days = [day for day in trend if day["net_amount"] > 0]
    average_daily_net = round(sum(day["net_amount"] for day in trend) / len(trend), 2) if trend else 0
    remaining_amount = max(campaign.total_amount - net_amount, 0)
    if average_daily_net > 0 and remaining_amount > 0:
        estimated_days = int((remaining_amount + average_daily_net - 1) // average_daily_net)
        estimated_date = (today + timezone.timedelta(days=estimated_days)).isoformat()
    elif remaining_amount == 0:
        estimated_days = 0
        estimated_date = today.isoformat()
    else:
        estimated_days = None
        estimated_date = None
    return {
        "active_fundraising_days": len(non_zero_days),
        "average_daily_net_amount": average_daily_net,
        "estimated_completion_days": estimated_days,
        "estimated_completion_date": estimated_date,
        "is_stalled": campaign.status == CampaignStatus.PUBLISHED and len(non_zero_days) == 0,
    }


def _calculate_campaign_intelligence_risk(*, campaign: Campaign) -> dict:
    """Summarize open risk-signal exposure for campaign intelligence."""
    open_signals = MadadkarRiskSignal.objects.filter(campaign=campaign, status=MadadkarRiskStatus.OPEN)
    return {
        "open_risk_signals": open_signals.count(),
        "high_or_critical_open_signals": open_signals.filter(severity__in=["high", "critical"]).count(),
    }


def _calculate_campaign_health_score(
    *,
    campaign: Campaign,
    success_count: int,
    failed_count: int,
    pending_count: int,
    refund_amount: int,
    gross_amount: int,
    donor_concentration: dict,
    open_risk_signals: int,
    velocity: dict,
) -> tuple[int, list[str]]:
    """Compute a transparent 0-100 campaign health score with flags."""
    score = 100
    flags: list[str] = []
    if failed_count > success_count and failed_count >= 3:
        score -= 20
        flags.append("payment_failure_pressure")
    if pending_count >= 5:
        score -= 10
        flags.append("pending_payment_backlog")
    refund_rate = (refund_amount / gross_amount) if gross_amount else 0
    if refund_rate >= 0.2:
        score -= 25
        flags.append("high_refund_rate")
    if donor_concentration["is_concentrated"]:
        score -= 15
        flags.append("top_donor_dependency")
    if open_risk_signals:
        score -= min(open_risk_signals * 10, 30)
        flags.append("open_risk_signals")
    if velocity["is_stalled"]:
        score -= 20
        flags.append("stalled_campaign")
    if campaign.has_deadline and campaign.deadline and campaign.deadline <= timezone.now() + timezone.timedelta(days=3) and campaign.remaining_shares > 0:
        score -= 10
        flags.append("deadline_pressure")
    return max(score, 0), flags


def _summarize_campaign_snapshots(snapshots: list[dict]) -> list[dict]:
    """Return compact intelligence rows for overview lists."""
    return [
        {
            "campaign_id": item["campaign_id"],
            "campaign_title": item["campaign_title"],
            "health_score": item["health"]["score"],
            "net_amount": item["financials"]["net_amount"],
            "net_progress_percent": item["financials"]["net_progress_percent"],
            "open_risk_signals": item["risk"]["open_risk_signals"],
            "flags": item["health"]["flags"],
        }
        for item in snapshots
    ]


# ---------------------------------------------------------------------------
# Donation receipt selectors — user/public/admin scope
# ---------------------------------------------------------------------------

def get_user_receipts_queryset(*, user_id: int) -> QuerySet[DonationReceipt]:
    """Return donation receipts owned by one user with eager loaded context."""
    return (
        DonationReceipt.objects
        .select_related("payment", "campaign", "user")
        .filter(user_id=user_id)
        .order_by("-issued_at", "-created_at")
    )


def get_user_receipt_by_id(*, user_id: int, receipt_id: int) -> DonationReceipt | None:
    """Return one receipt only if it belongs to the requesting user."""
    return get_user_receipts_queryset(user_id=user_id).filter(pk=receipt_id).first()


def get_receipt_by_number(*, receipt_number: str) -> DonationReceipt | None:
    """Return one receipt by public receipt number for verification."""
    return DonationReceipt.objects.select_related("payment", "campaign", "user").filter(receipt_number=receipt_number).first()


def get_admin_receipt_by_id(*, receipt_id: int) -> DonationReceipt | None:
    """Return one receipt for audited admin actions."""
    return DonationReceipt.objects.select_related("payment", "campaign", "user").filter(pk=receipt_id).first()


# ---------------------------------------------------------------------------
# Reconciliation selectors — admin scope
# ---------------------------------------------------------------------------

def get_admin_reconciliation_batches_queryset() -> QuerySet[PaymentReconciliationBatch]:
    """Return provider settlement reconciliation batches for admin review."""
    return PaymentReconciliationBatch.objects.order_by("-created_at")


def get_admin_reconciliation_batch_by_id(*, batch_id: int) -> PaymentReconciliationBatch | None:
    """Return one reconciliation batch for admin detail/export actions."""
    return get_admin_reconciliation_batches_queryset().filter(pk=batch_id).first()


def get_admin_reconciliation_items_queryset(*, batch: PaymentReconciliationBatch) -> QuerySet[PaymentReconciliationItem]:
    """Return reconciliation items for one batch with payment eager loading."""
    return batch.items.select_related("payment").order_by("created_at", "id")


# ---------------------------------------------------------------------------
# Disbursement selectors — admin scope
# ---------------------------------------------------------------------------

def get_admin_disbursements_queryset() -> QuerySet[CampaignDisbursement]:
    """Return disbursement workflow rows with campaign/user eager loading."""
    return (
        CampaignDisbursement.objects
        .select_related("campaign", "requested_by", "reviewed_by", "paid_by")
        .order_by("-created_at")
    )


def get_admin_disbursement_by_id(*, disbursement_id: int) -> CampaignDisbursement | None:
    """Return one disbursement workflow row for admin action."""
    return get_admin_disbursements_queryset().filter(pk=disbursement_id).first()


def get_campaign_disbursable_summary(*, campaign: Campaign) -> dict:
    """Return campaign disbursable amount summary for allocation decisions."""
    active = CampaignDisbursement.objects.filter(
        campaign=campaign,
        status__in=[DisbursementStatus.REQUESTED, DisbursementStatus.APPROVED, DisbursementStatus.PAID],
    )
    committed = active.aggregate(total=Sum("amount"))["total"] or 0
    paid = active.filter(status=DisbursementStatus.PAID).aggregate(total=Sum("amount"))["total"] or 0
    return {
        "campaign_id": campaign.pk,
        "net_effective_amount": campaign.purchased_amount,
        "committed_disbursement_amount": committed,
        "paid_disbursement_amount": paid,
        "disbursable_amount": max(campaign.purchased_amount - committed, 0),
    }


# ---------------------------------------------------------------------------
# Public transparency selectors
# ---------------------------------------------------------------------------

def get_public_campaign_transparency(*, campaign: Campaign) -> dict:
    """Build public-safe financial transparency snapshot for one visible campaign."""
    payments = Payment.objects.filter(participation__campaign=campaign, status=PaymentStatus.SUCCESS)
    refunds = PaymentRefund.objects.filter(payment__participation__campaign=campaign, status=RefundStatus.COMPLETED)
    adjustments = CampaignFinancialAdjustment.objects.filter(campaign=campaign, status=FinancialAdjustmentStatus.APPLIED)
    disbursements = CampaignDisbursement.objects.filter(campaign=campaign)
    gross_amount = payments.aggregate(total=Sum("amount"))["total"] or 0
    refund_amount = refunds.aggregate(total=Sum("amount"))["total"] or 0
    adjustment_delta = sum(adjustment.signed_amount for adjustment in adjustments)
    net_raised = max(gross_amount - refund_amount + adjustment_delta, 0)
    paid_disbursements = disbursements.filter(status=DisbursementStatus.PAID).aggregate(total=Sum("amount"))["total"] or 0
    committed_disbursements = disbursements.filter(
        status__in=[DisbursementStatus.REQUESTED, DisbursementStatus.APPROVED, DisbursementStatus.PAID],
    ).aggregate(total=Sum("amount"))["total"] or 0
    receipt_count = DonationReceipt.objects.filter(campaign=campaign).count()
    return {
        "campaign_id": campaign.pk,
        "campaign_title": campaign.title,
        "campaign_slug": campaign.slug,
        "sponsor_name": campaign.sponsor.name,
        "generated_at": timezone.now().isoformat(),
        "target_amount": campaign.total_amount,
        "gross_raised_amount": gross_amount,
        "completed_refund_amount": refund_amount,
        "applied_adjustment_delta": adjustment_delta,
        "net_raised_amount": net_raised,
        "paid_disbursement_amount": paid_disbursements,
        "committed_disbursement_amount": committed_disbursements,
        "remaining_disbursable_amount": max(net_raised - committed_disbursements, 0),
        "receipt_count": receipt_count,
        "successful_payment_count": payments.count(),
        "completed_refund_count": refunds.count(),
        "paid_disbursement_count": disbursements.filter(status=DisbursementStatus.PAID).count(),
        "net_progress_percent": round((net_raised / campaign.total_amount) * 100, 2) if campaign.total_amount else 0,
        "public_note": "این گزارش عمومی، بدون نمایش اطلاعات خصوصی مشارکت‌کنندگان تولید شده است.",
    }
