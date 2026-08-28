"""Read-side selectors for unified admin command center.

دو مشکل کارایی این ماژول
=========================
۱. **تعداد کوئری.** هر شمارنده یک ``COUNT(*)`` مستقل بود، حتی وقتی چند
   شمارنده روی *یک جدول* و فقط با شرط متفاوت محاسبه می‌شدند. نتیجه ۴۴ کوئری
   برای یک درخواست بود. حالا شمارنده‌های هم‌جدول با conditional aggregation
   (``Count(filter=Q(...))``) در یک پیمایش جمع می‌شوند. مقادیر دقیقاً همان
   قبل هستند؛ فقط به‌جای N بار اسکن جدول، یک بار اسکن می‌شود.

۲. **نبود کش.** این endpoint قرارداد کارایی ۲۰۰۰ میلی‌ثانیه دارد
   (``"/api/v1/admin/*"``) ولی هیچ کشی نداشت، و روی پستگرس ``COUNT(*)`` بدون
   ``WHERE`` یعنی sequential scan کامل. با چند میلیون ردیف در ``Payment`` یا
   ``SupportTicket``، هر بار باز کردن داشبورد چند ثانیه CPU دیتابیس می‌خورد
   و چند ادمین همزمان می‌توانستند دیتابیس را به زانو دربیاورند.

   شمارنده‌ها حالا با stale-while-revalidate کش می‌شوند.

چرا تسک دوره‌ای نگذاشتیم
-------------------------
گزینهٔ بدیهی یک تسک Celery بود که هر دقیقه snapshot بسازد. عمداً انتخاب
*نشد*: آن کار یعنی اجرای دائمی این aggregateهای سنگین حتی وقتی هیچ ادمینی
داشبورد را باز نکرده — یعنی تبدیل یک هزینهٔ گاه‌به‌گاه به یک بار ثابت روی
دیتابیس. با SWR فقط اولین درخواست پس از انقضای نرم هزینه می‌دهد و بقیه از
کش می‌خوانند؛ وقتی کسی نگاه نمی‌کند، هیچ هزینه‌ای وجود ندارد.

چه چیزی کش *نمی‌شود*
---------------------
``health`` و ``providers`` هر بار زنده محاسبه می‌شوند. کش کردن وضعیت سلامت
فعالانه مضر است: ادمینی که می‌پرسد «آیا Redis بالاست؟» به پاسخ همین لحظه
نیاز دارد، نه به پاسخ دو دقیقه پیش.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.core.cache import cache_get_or_set_swr, make_cache_key

#: فضای نام کش شمارنده‌های مرکز فرماندهی.
COMMAND_CENTER_CACHE_NAMESPACE = "command_center:summary"

#: پس از این مدت مقدار کش «کهنه» محسوب می‌شود و اولین درخواست بعدی آن را
#: تازه می‌کند. یک دقیقه برای یک داشبورد عملیاتی تعادل درستی بین تازگی و
#: بار دیتابیس است.
COMMAND_CENTER_SOFT_TTL_SECONDS = 60

#: حداکثر عمر مجاز مقدار کهنه. اگر تازه‌سازی خطا بدهد، تا این مدت مقدار
#: قبلی سرو می‌شود (fail-open) به‌جای اینکه داشبورد کامل از کار بیفتد.
COMMAND_CENTER_HARD_TTL_SECONDS = 300

#: قفل ضد dogpile: وقتی مقدار کهنه شد فقط یک درخواست بازمحاسبه می‌کند.
COMMAND_CENTER_LOCK_TTL_SECONDS = 20


def get_command_center_summary() -> dict[str, Any]:
    """Return a cross-app operational summary for admins.

    شمارنده‌ها از کش SWR می‌آیند و وضعیت سلامت/providerها زنده محاسبه
    می‌شوند. ``counters_generated_at`` می‌گوید شمارنده‌ها واقعاً چه زمانی
    محاسبه شده‌اند تا ادمین بداند چقدر کهنه‌اند.
    """
    counters = cache_get_or_set_swr(
        key=make_cache_key(COMMAND_CENTER_CACHE_NAMESPACE, "v1"),
        factory=build_command_center_counters,
        soft_ttl=COMMAND_CENTER_SOFT_TTL_SECONDS,
        hard_ttl=COMMAND_CENTER_HARD_TTL_SECONDS,
        lock_ttl=COMMAND_CENTER_LOCK_TTL_SECONDS,
    )
    return {
        "generated_at": timezone.now(),
        "counters_generated_at": counters.get("counters_generated_at"),
        "support": counters["support"],
        "kindness_wall": counters["kindness_wall"],
        "tabyin": counters["tabyin"],
        "public_reports": counters["public_reports"],
        "r4j": counters["r4j"],
        "madadkar": counters["madadkar"],
        "lms": counters["lms"],
        "notifications": counters["notifications"],
        "activity": counters["activity"],
        "providers": _provider_summary(),
        "health": _health_summary(),
    }


def build_command_center_counters() -> dict[str, Any]:
    """Compute every cacheable counter section from the database."""
    return {
        "counters_generated_at": timezone.now().isoformat(),
        "support": _support_summary(),
        "kindness_wall": _kindness_summary(),
        "tabyin": _tabyin_summary(),
        "public_reports": _public_reports_summary(),
        "r4j": _r4j_summary(),
        "madadkar": _madadkar_summary(),
        "lms": _lms_summary(),
        "notifications": _notifications_summary(),
        "activity": _activity_summary(),
    }


def _support_summary() -> dict[str, int]:
    """Return support desk queue counters in a single aggregate query."""
    from apps.support_desk.choices import TicketStatus
    from apps.support_desk.models import SupportTicket

    is_open = ~Q(status__in=[TicketStatus.CLOSED, TicketStatus.ARCHIVED, TicketStatus.SPAM])
    return SupportTicket.all_objects.aggregate(
        total_tickets=Count("pk"),
        open_tickets=Count("pk", filter=is_open),
        unassigned_tickets=Count("pk", filter=is_open & Q(assigned_to__isnull=True)),
        sla_breached_tickets=Count("pk", filter=is_open & Q(sla_breached_at__isnull=False)),
        escalated_tickets=Count("pk", filter=is_open & Q(status=TicketStatus.ESCALATED)),
    )


def _kindness_summary() -> dict[str, int]:
    """Return Kindness Wall operational counters."""
    from apps.kindness_wall.choices import DuplicateStatus, ListingStatus, ReportStatus
    from apps.kindness_wall.models import (
        KindnessContactReveal,
        KindnessDuplicateCandidate,
        KindnessListing,
        KindnessListingReport,
        KindnessRiskSignal,
    )

    # ``objects`` و ``all_objects`` دو manager متفاوت‌اند (soft-delete)، پس
    # این دو شمارنده قابل ادغام در یک کوئری نیستند.
    return {
        "pending_listings": KindnessListing.all_objects.filter(
            status=ListingStatus.PENDING_REVIEW
        ).count(),
        "published_listings": KindnessListing.objects.published().count(),
        "pending_reports": KindnessListingReport.objects.filter(
            status=ReportStatus.PENDING
        ).count(),
        "active_duplicate_candidates": KindnessDuplicateCandidate.objects.filter(
            status=DuplicateStatus.ACTIVE
        ).count(),
        "contact_reveals_total": KindnessContactReveal.objects.count(),
        "open_risk_signals": KindnessRiskSignal.objects.filter(status="open").count(),
    }


def _tabyin_summary() -> dict[str, int]:
    """Return Tabyin content/submission counters."""
    from apps.tabyin.choices import ContentOrigin, SubmissionStatus
    from apps.tabyin.models import TabyinContent

    submissions = TabyinContent.all_objects.aggregate(
        pending_user_submissions=Count(
            "pk",
            filter=Q(
                origin=ContentOrigin.USER_SUBMITTED,
                submission_status=SubmissionStatus.PENDING_REVIEW,
            ),
        ),
        rejected_user_submissions=Count(
            "pk",
            filter=Q(
                origin=ContentOrigin.USER_SUBMITTED, submission_status=SubmissionStatus.REJECTED
            ),
        ),
        deleted_in_source=Count("pk", filter=Q(is_deleted_in_source=True)),
    )
    return {
        "active_contents": TabyinContent.objects.count(),
        **submissions,
    }


def _public_reports_summary() -> dict[str, int]:
    """Return public report counters in a single aggregate query."""
    from apps.public_reports.choices import ReportStatus
    from apps.public_reports.models import Report

    return Report.objects.aggregate(
        pending_reports=Count("pk", filter=Q(status=ReportStatus.PENDING)),
        reviewing_reports=Count("pk", filter=Q(status=ReportStatus.REVIEWING)),
        approved_reports=Count("pk", filter=Q(status=ReportStatus.APPROVED)),
        rejected_reports=Count("pk", filter=Q(status=ReportStatus.REJECTED)),
    )


def _r4j_summary() -> dict[str, int]:
    """Return R4J moderation and bounty counters."""
    from apps.r4j.choices import BountyStatus, ReportStatus
    from apps.r4j.models import R4JBounty, R4JCriminal, R4JReport

    reports = R4JReport.objects.aggregate(
        pending_reports=Count("pk", filter=Q(status=ReportStatus.PENDING)),
        cancel_requested_reports=Count("pk", filter=Q(status=ReportStatus.CANCEL_REQUESTED)),
    )
    return {
        "published_criminals": R4JCriminal.objects.filter(is_published=True).count(),
        **reports,
        "active_bounties": R4JBounty.objects.filter(status=BountyStatus.ACTIVE).count(),
    }


def _madadkar_summary() -> dict[str, int]:
    """Return Madadkar campaign/payment counters."""
    from apps.madadkar.choices import CampaignStatus, MadadkarRiskStatus, PaymentStatus
    from apps.madadkar.models import (
        Campaign,
        MadadkarRiskSignal,
        Payment,
        PaymentReconciliationBatch,
    )

    campaigns = Campaign.objects.aggregate(
        published_campaigns=Count("pk", filter=Q(status=CampaignStatus.PUBLISHED)),
        completed_campaigns=Count("pk", filter=Q(status=CampaignStatus.COMPLETED)),
    )
    payments = Payment.objects.aggregate(
        pending_payments=Count("pk", filter=Q(status=PaymentStatus.PENDING)),
        failed_payments=Count("pk", filter=Q(status=PaymentStatus.FAILED)),
        successful_payments=Count("pk", filter=Q(status=PaymentStatus.SUCCESS)),
    )
    reconciliation = PaymentReconciliationBatch.objects.aggregate(
        reconciliation_batches=Count("pk"),
        reconciliation_mismatches=Sum("mismatch_count"),
    )
    return {
        **campaigns,
        **payments,
        "open_risk_signals": MadadkarRiskSignal.objects.filter(
            status=MadadkarRiskStatus.OPEN
        ).count(),
        "reconciliation_batches": reconciliation["reconciliation_batches"],
        "reconciliation_mismatches": reconciliation["reconciliation_mismatches"] or 0,
    }


def _lms_summary() -> dict[str, int]:
    """Return LMS learning/certificate counters."""
    from apps.lms.choices import CertificateStatus, CourseStatus, EnrollmentStatus
    from apps.lms.models import Certificate, Course, Enrollment

    enrollments = Enrollment.objects.aggregate(
        active_enrollments=Count("pk", filter=Q(status=EnrollmentStatus.ACTIVE)),
        completed_enrollments=Count("pk", filter=Q(status=EnrollmentStatus.COMPLETED)),
    )
    certificates = Certificate.objects.aggregate(
        issued_certificates=Count("pk", filter=Q(status=CertificateStatus.ISSUED)),
        revoked_certificates=Count("pk", filter=Q(status=CertificateStatus.REVOKED)),
    )
    return {
        "published_courses": Course.objects.filter(status=CourseStatus.PUBLISHED).count(),
        **enrollments,
        **certificates,
    }


def _notifications_summary() -> dict[str, int]:
    """Return notification engine counters."""
    from apps.notifications.choices import NotificationDeliveryStatus, NotificationEventStatus
    from apps.notifications.models import NotificationDelivery, NotificationEvent

    events = NotificationEvent.objects.aggregate(
        pending_events=Count("pk", filter=Q(status=NotificationEventStatus.PENDING)),
        failed_events=Count("pk", filter=Q(status=NotificationEventStatus.FAILED)),
    )
    deliveries = NotificationDelivery.objects.aggregate(
        pending_deliveries=Count("pk", filter=Q(status=NotificationDeliveryStatus.PENDING)),
        failed_deliveries=Count("pk", filter=Q(status=NotificationDeliveryStatus.FAILED)),
        unread_deliveries=Count("pk", filter=~Q(status=NotificationDeliveryStatus.READ)),
    )
    return {**events, **deliveries}


def _activity_summary() -> dict[str, int]:
    """Return recent activity counters in a single aggregate query."""
    from apps.activity.models import UserActivity

    since = timezone.now() - timezone.timedelta(days=1)
    return UserActivity.objects.aggregate(
        total_activities=Count("pk"),
        activities_last_24h=Count("pk", filter=Q(created_at__gte=since)),
    )


def _provider_summary() -> dict[str, dict[str, object]]:
    """Return provider readiness summary."""
    from apps.core.provider_readiness import get_provider_readiness_summary

    return get_provider_readiness_summary()


def _health_summary() -> dict[str, object]:
    """Return lightweight health status summary without leaking secrets."""
    from apps.core.health.checks import aggregate_status, build_readiness_checks

    checks = build_readiness_checks()
    return {
        "status": aggregate_status(checks),
        "checks": {
            name: {"status": value.get("status"), "latency_ms": value.get("latency_ms")}
            for name, value in checks.items()
        },
    }
