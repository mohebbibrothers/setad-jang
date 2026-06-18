# apps/r4j/selectors.py
"""
Selectors اپ R4J — query layer.

تمام queryهای read-side از اینجا عبور می‌کنند تا:
- N+1 جلوگیری شود (با prefetch/select_related)
- visibility logic در یک نقطه centralize شود
- public/admin scope ها از هم جدا بمانند

اصول طراحی:
- get_public_*: فقط رکوردهای published + is_active
- get_admin_*: شامل draft و soft-deleted (با manager all_objects)
- helper functions برای lookup با slug یا id

بخش‌ها:
1. Criminal — public scope
2. Criminal — admin scope
3. Nested resources — admin scope
4. Report — user scope
5. Report — admin scope
6. Bounty — user scope
7. Bounty — admin scope
8. Helpers + visibility
"""

from __future__ import annotations

from typing import Final

from django.db.models import Prefetch, QuerySet

from .models import (
    R4JBounty,
    R4JCaseEvent,
    R4JCriminal,
    R4JCriminalAlias,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JCriminalPhone,
    R4JCriminalPhoto,
    R4JCriminalSocial,
    R4JEvidenceCustodyEvent,
    R4JInvestigationCase,
    R4JReport,
    R4JReportAttachment,
    R4JReportFieldChange,
)

# ============================================================
# Public visibility defaults
# ============================================================

#: تنظیمات پیش‌فرض نمایش فیلدها به public.
#: اگر برای یک criminal خاص override در R4JCriminalFieldVisibility باشد،
#: آن مقدار اولویت دارد.
PUBLIC_DEFAULT_VISIBILITY: Final[dict[str, bool]] = {
    "national_code": False,
    "birth_date": True,
    "gender": True,
    "country": True,
    "province": True,
    "city": True,
    "description": True,
    "crimes_summary": True,
    "other_info": True,
}


# ============================================================
# Criminal — public scope
# ============================================================


def get_public_criminals_queryset() -> QuerySet[R4JCriminal]:
    """
    لیست published + active criminals با prefetch بهینه برای رندر کارت.

    این queryset برای endpoint عمومی لیست استفاده می‌شود.
    """
    return (
        R4JCriminal.published
        .all()
        .prefetch_related(
            Prefetch(
                "photos",
                queryset=R4JCriminalPhoto.objects.filter(is_active=True).order_by(
                    "order", "-created_at",
                ),
            ),
        )
    )


def get_public_criminal_detail(
    *,
    lookup: str | int,
) -> R4JCriminal | None:
    """
    دریافت یک criminal منتشرشده با id یا slug.

    تمام nested resources را با visibility filter آماده می‌کند:
    - فقط phone/social/attachment با is_public=True
    - تمام photos
    - تمام aliases
    - field_visibility برای محاسبه‌ی visibility فیلدهای core
    """
    queryset = (
        R4JCriminal.published
        .all()
        .prefetch_related(
            Prefetch(
                "photos",
                queryset=R4JCriminalPhoto.objects.filter(is_active=True).order_by(
                    "order", "-created_at",
                ),
            ),
            Prefetch(
                "phones",
                queryset=R4JCriminalPhone.objects.filter(
                    is_active=True, is_public=True,
                ),
            ),
            Prefetch(
                "socials",
                queryset=R4JCriminalSocial.objects.filter(
                    is_active=True, is_public=True,
                ),
            ),
            Prefetch(
                "attachments",
                queryset=R4JCriminalAttachment.objects.filter(
                    is_active=True, is_public=True,
                ),
            ),
            Prefetch(
                "aliases",
                queryset=R4JCriminalAlias.objects.filter(is_active=True),
            ),
            Prefetch(
                "field_visibility",
                queryset=R4JCriminalFieldVisibility.objects.filter(is_active=True),
            ),
        )
    )

    return _lookup_criminal(queryset, lookup)


# ============================================================
# Criminal — admin scope
# ============================================================


def get_admin_criminals_queryset() -> QuerySet[R4JCriminal]:
    """
    لیست تمام criminals — شامل draft و soft-deleted.

    برای admin panel که نیاز است وضعیت واقعی همه چیز را ببیند.
    """
    return (
        R4JCriminal.all_objects.all()
        .prefetch_related(
            Prefetch(
                "photos",
                queryset=R4JCriminalPhoto.all_objects.order_by(
                    "order", "-created_at",
                ),
            ),
        )
    )


def get_admin_criminal_detail(*, lookup: str | int) -> R4JCriminal | None:
    """دریافت یک criminal با تمام nested data — برای admin."""
    queryset = (
        R4JCriminal.all_objects.all()
        .prefetch_related(
            "photos",
            "phones",
            "socials",
            "attachments",
            "aliases",
            "field_visibility",
        )
    )
    return _lookup_criminal(queryset, lookup)


def get_admin_criminal_by_id(criminal_id: int) -> R4JCriminal | None:
    """lookup سریع برای nested resource viewها (با id)."""
    try:
        return R4JCriminal.all_objects.get(pk=criminal_id)
    except R4JCriminal.DoesNotExist:
        return None


# ============================================================
# Nested resources — admin scope
# ============================================================


def get_admin_phones(*, criminal_id: int) -> QuerySet[R4JCriminalPhone]:
    """تمام شماره‌های تماس یک criminal — برای admin."""
    return R4JCriminalPhone.all_objects.filter(criminal_id=criminal_id)


def get_admin_phone_by_id(
    *, criminal_id: int, phone_id: int,
) -> R4JCriminalPhone | None:
    """دریافت یک شماره با id و criminal_id."""
    try:
        return R4JCriminalPhone.all_objects.get(pk=phone_id, criminal_id=criminal_id)
    except R4JCriminalPhone.DoesNotExist:
        return None


def get_admin_socials(*, criminal_id: int) -> QuerySet[R4JCriminalSocial]:
    """تمام شبکه‌های اجتماعی یک criminal — برای admin."""
    return R4JCriminalSocial.all_objects.filter(criminal_id=criminal_id)


def get_admin_social_by_id(
    *, criminal_id: int, social_id: int,
) -> R4JCriminalSocial | None:
    """دریافت یک social با id و criminal_id."""
    try:
        return R4JCriminalSocial.all_objects.get(pk=social_id, criminal_id=criminal_id)
    except R4JCriminalSocial.DoesNotExist:
        return None


def get_admin_aliases(*, criminal_id: int) -> QuerySet[R4JCriminalAlias]:
    """تمام aliases یک criminal — برای admin."""
    return R4JCriminalAlias.all_objects.filter(criminal_id=criminal_id)


def get_admin_alias_by_id(
    *, criminal_id: int, alias_id: int,
) -> R4JCriminalAlias | None:
    """دریافت یک alias با id و criminal_id."""
    try:
        return R4JCriminalAlias.all_objects.get(pk=alias_id, criminal_id=criminal_id)
    except R4JCriminalAlias.DoesNotExist:
        return None


def get_admin_photos(*, criminal_id: int) -> QuerySet[R4JCriminalPhoto]:
    """تمام عکس‌های یک criminal مرتب‌شده — برای admin."""
    return R4JCriminalPhoto.all_objects.filter(criminal_id=criminal_id).order_by(
        "order", "-created_at",
    )


def get_admin_photo_by_id(
    *, criminal_id: int, photo_id: int,
) -> R4JCriminalPhoto | None:
    """دریافت یک photo با id و criminal_id."""
    try:
        return R4JCriminalPhoto.all_objects.get(pk=photo_id, criminal_id=criminal_id)
    except R4JCriminalPhoto.DoesNotExist:
        return None


def get_admin_attachments(*, criminal_id: int) -> QuerySet[R4JCriminalAttachment]:
    """تمام اسناد یک criminal — برای admin."""
    return R4JCriminalAttachment.all_objects.filter(criminal_id=criminal_id)


def get_admin_attachment_by_id(
    *, criminal_id: int, attachment_id: int,
) -> R4JCriminalAttachment | None:
    """دریافت یک attachment با id و criminal_id."""
    try:
        return R4JCriminalAttachment.all_objects.get(
            pk=attachment_id, criminal_id=criminal_id,
        )
    except R4JCriminalAttachment.DoesNotExist:
        return None


def get_admin_field_visibility(
    *, criminal_id: int,
) -> QuerySet[R4JCriminalFieldVisibility]:
    """تمام visibility overrideهای یک criminal — برای admin."""
    return R4JCriminalFieldVisibility.all_objects.filter(criminal_id=criminal_id)


# ============================================================
# Report — user scope
# ============================================================


def get_user_reports_queryset(*, user_id: int) -> QuerySet[R4JReport]:
    """
    لیست گزارش‌های یک کاربر خاص — برای my-reports endpoint.

    شامل prefetch field_changes و attachments برای جلوگیری از N+1.
    """
    return (
        R4JReport.objects.filter(submitted_by_id=user_id)
        .select_related("criminal")
        .prefetch_related(
            Prefetch(
                "field_changes",
                queryset=R4JReportFieldChange.objects.order_by("field_name"),
            ),
            Prefetch(
                "attachments",
                queryset=R4JReportAttachment.objects.order_by("-created_at"),
            ),
        )
        .order_by("-created_at")
    )


def get_user_report_by_id(
    *, user_id: int, report_id: int,
) -> R4JReport | None:
    """
    دریافت یک گزارش خاص از یک کاربر — با IDOR protection.

    submitted_by_id در query گنجانده شده تا کاربر نتواند با
    تغییر report_id به گزارش دیگران دسترسی پیدا کند.
    """
    try:
        return (
            R4JReport.objects.filter(
                pk=report_id,
                submitted_by_id=user_id,
            )
            .select_related("criminal", "reviewed_by")
            .prefetch_related(
                Prefetch(
                    "field_changes",
                    queryset=R4JReportFieldChange.objects.order_by("field_name"),
                ),
                Prefetch(
                    "attachments",
                    queryset=R4JReportAttachment.objects.order_by("-created_at"),
                ),
            )
            .get()
        )
    except R4JReport.DoesNotExist:
        return None


# ============================================================
# Report — admin scope
# ============================================================


def get_admin_reports_queryset() -> QuerySet[R4JReport]:
    """
    لیست تمام گزارشات — برای admin.

    شامل prefetch کامل برای جلوگیری از N+1 در list rendering.
    """
    return (
        R4JReport.objects.all()
        .select_related("criminal", "submitted_by", "reviewed_by")
        .prefetch_related(
            Prefetch(
                "field_changes",
                queryset=R4JReportFieldChange.objects.order_by("field_name"),
            ),
            Prefetch(
                "attachments",
                queryset=R4JReportAttachment.objects.order_by("-created_at"),
            ),
        )
        .order_by("-created_at")
    )


def get_admin_report_by_id(*, report_id: int) -> R4JReport | None:
    """دریافت یک گزارش برای admin — بدون IDOR filter (ادمین همه را می‌بیند)."""
    try:
        return (
            R4JReport.objects.filter(pk=report_id)
            .select_related("criminal", "submitted_by", "reviewed_by")
            .prefetch_related(
                Prefetch(
                    "field_changes",
                    queryset=R4JReportFieldChange.objects.order_by("field_name"),
                ),
                Prefetch(
                    "attachments",
                    queryset=R4JReportAttachment.objects.order_by("-created_at"),
                ),
            )
            .get()
        )
    except R4JReport.DoesNotExist:
        return None


# ============================================================
# Bounty — user scope
# ============================================================


def get_user_bounties_queryset(*, user_id: int) -> QuerySet[R4JBounty]:
    """
    لیست bountyهای کاربر جاری.

    منطق:
    - فقط bountyهای متعلق به user جاری
    - select_related روی criminal برای جلوگیری از N+1
    - مرتب‌سازی نزولی بر اساس created_at

    این queryset برای endpoint:
        GET /api/v1/r4j/me/bounties/
    استفاده می‌شود.
    """
    return (
        R4JBounty.objects.filter(user_id=user_id)
        .select_related("criminal")
        .order_by("-created_at")
    )


def get_user_bounty_by_id(
    *,
    user_id: int,
    bounty_id: int,
) -> R4JBounty | None:
    """
    دریافت یک bounty خاص برای user جاری با محافظت در برابر IDOR.

    فقط زمانی bounty برگردانده می‌شود که هم:
    - id درست باشد
    - owner همان user جاری باشد

    Args:
        user_id: شناسه کاربر جاری.
        bounty_id: شناسه bounty.

    Returns:
        R4JBounty | None
    """
    try:
        return (
            R4JBounty.objects.filter(
                pk=bounty_id,
                user_id=user_id,
            )
            .select_related("criminal")
            .get()
        )
    except R4JBounty.DoesNotExist:
        return None


# ============================================================
# Bounty — admin scope
# ============================================================


def get_admin_bounties_queryset() -> QuerySet[R4JBounty]:
    """
    لیست تمام bountyها برای admin.

    شامل:
    - active
    - cancel_requested
    - canceled

    با select_related برای جلوگیری از N+1 در list rendering.
    """
    return (
        R4JBounty.objects.all()
        .select_related("criminal", "user")
        .order_by("-created_at")
    )


def get_admin_bounty_by_id(*, bounty_id: int) -> R4JBounty | None:
    """
    دریافت یک bounty خاص برای admin.

    Args:
        bounty_id: شناسه bounty.

    Returns:
        R4JBounty | None
    """
    try:
        return (
            R4JBounty.objects.filter(pk=bounty_id)
            .select_related("criminal", "user")
            .get()
        )
    except R4JBounty.DoesNotExist:
        return None


# ============================================================
# Helpers
# ============================================================


def _lookup_criminal(
    queryset: QuerySet[R4JCriminal],
    lookup: str | int,
) -> R4JCriminal | None:
    """lookup با id (اگر عدد) یا slug (اگر رشته)."""
    try:
        if isinstance(lookup, int) or (
            isinstance(lookup, str) and lookup.isdigit()
        ):
            return queryset.get(pk=int(lookup))
        return queryset.get(slug=str(lookup))
    except R4JCriminal.DoesNotExist:
        return None


def compute_visibility_map(
    criminal: R4JCriminal,
) -> dict[str, bool]:
    """
    محاسبه map نهایی نمایش فیلدها به public برای یک criminal.

    منطق:
    - default از PUBLIC_DEFAULT_VISIBILITY
    - override از R4JCriminalFieldVisibility (در صورت وجود)
    """
    overrides = {
        fv.field_name: fv.is_public for fv in criminal.field_visibility.all()
    }
    return {**PUBLIC_DEFAULT_VISIBILITY, **overrides}


# ============================================================
# Evidence custody — admin scope
# ============================================================

def get_admin_evidence_custody_events() -> QuerySet[R4JEvidenceCustodyEvent]:
    """Return all evidence custody events for admin forensic review."""
    return R4JEvidenceCustodyEvent.objects.select_related(
        "criminal_attachment",
        "report_attachment",
        "actor",
    ).order_by("-created_at")


def get_admin_evidence_custody_event_by_id(*, event_id: int) -> R4JEvidenceCustodyEvent | None:
    """Return one custody event by id."""
    return get_admin_evidence_custody_events().filter(pk=event_id).first()

# ============================================================
# Investigation Cases — admin operational read side
# ============================================================


def get_admin_investigation_cases_queryset() -> QuerySet[R4JInvestigationCase]:
    """Admin list queryset for operational R4J cases with stable joins."""
    return (
        R4JInvestigationCase.objects.select_related(
            "report",
            "criminal",
            "assigned_to",
            "triaged_by",
            "closed_by",
        )
        .prefetch_related("events")
        .order_by("-created_at")
    )


def get_admin_investigation_case_by_number(*, case_number: str) -> R4JInvestigationCase | None:
    """Fetch an investigation case by human case number."""
    try:
        return get_admin_investigation_cases_queryset().get(case_number=case_number)
    except R4JInvestigationCase.DoesNotExist:
        return None


def get_admin_investigation_case_by_id(*, case_id: int) -> R4JInvestigationCase | None:
    """Fetch an investigation case by primary key."""
    try:
        return get_admin_investigation_cases_queryset().get(pk=case_id)
    except R4JInvestigationCase.DoesNotExist:
        return None


def get_admin_investigation_case_timeline(*, case: R4JInvestigationCase) -> QuerySet[R4JCaseEvent]:
    """Read immutable timeline for a case."""
    return case.events.select_related("actor").order_by("created_at", "id")


def get_r4j_case_operations_overview() -> dict[str, object]:
    """Aggregate operational counters for the R4J admin command view."""
    from django.db.models import Count
    from django.utils import timezone

    now = timezone.now()
    queryset = R4JInvestigationCase.objects.all()
    by_status = {row["status"]: row["count"] for row in queryset.values("status").annotate(count=Count("id"))}
    by_priority = {row["priority"]: row["count"] for row in queryset.values("priority").annotate(count=Count("id"))}
    return {
        "total_cases": queryset.count(),
        "unassigned_cases": queryset.filter(assigned_to__isnull=True).exclude(status__in=["resolved", "rejected", "closed"]).count(),
        "overdue_first_response": queryset.filter(first_response_due_at__lt=now).exclude(status__in=["resolved", "rejected", "closed"]).count(),
        "overdue_resolution": queryset.filter(resolution_due_at__lt=now).exclude(status__in=["resolved", "rejected", "closed"]).count(),
        "by_status": by_status,
        "by_priority": by_priority,
    }


def get_overdue_investigation_cases() -> QuerySet[R4JInvestigationCase]:
    """Cases that breached first-response or resolution due dates."""
    from django.db.models import Q
    from django.utils import timezone

    now = timezone.now()
    return get_admin_investigation_cases_queryset().filter(
        Q(first_response_due_at__lt=now) | Q(resolution_due_at__lt=now),
    ).exclude(status__in=["resolved", "rejected", "closed"])


def get_unassigned_investigation_cases() -> QuerySet[R4JInvestigationCase]:
    """Mutable cases that have not been assigned yet."""
    return get_admin_investigation_cases_queryset().filter(
        assigned_to__isnull=True,
    ).exclude(status__in=["resolved", "rejected", "closed"])
