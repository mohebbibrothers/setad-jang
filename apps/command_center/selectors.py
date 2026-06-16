"""Read-side selectors for unified admin command center."""

from __future__ import annotations

from typing import Any

from django.db.models import Sum
from django.utils import timezone


def get_command_center_summary() -> dict[str, Any]:
    """Return a cross-app operational summary for admins."""
    return {
        "generated_at": timezone.now(),
        "support": _support_summary(),
        "kindness_wall": _kindness_summary(),
        "tabyin": _tabyin_summary(),
        "public_reports": _public_reports_summary(),
        "r4j": _r4j_summary(),
        "madadkar": _madadkar_summary(),
        "lms": _lms_summary(),
        "notifications": _notifications_summary(),
        "activity": _activity_summary(),
        "providers": _provider_summary(),
        "health": _health_summary(),
    }


def _support_summary() -> dict[str, int]:
    """Return support desk queue counters."""
    from apps.support_desk.choices import TicketStatus
    from apps.support_desk.models import SupportTicket

    tickets = SupportTicket.all_objects.all()
    open_tickets = tickets.exclude(status__in=[TicketStatus.CLOSED, TicketStatus.ARCHIVED, TicketStatus.SPAM])
    return {
        "total_tickets": tickets.count(),
        "open_tickets": open_tickets.count(),
        "unassigned_tickets": open_tickets.filter(assigned_to__isnull=True).count(),
        "sla_breached_tickets": open_tickets.filter(sla_breached_at__isnull=False).count(),
        "escalated_tickets": open_tickets.filter(status=TicketStatus.ESCALATED).count(),
    }


def _kindness_summary() -> dict[str, int]:
    """Return Kindness Wall operational counters."""
    from apps.kindness_wall.choices import DuplicateStatus, ListingStatus, ReportStatus
    from apps.kindness_wall.models import (
        KindnessContactReveal,
        KindnessDuplicateCandidate,
        KindnessListing,
        KindnessListingReport,
    )

    return {
        "pending_listings": KindnessListing.all_objects.filter(status=ListingStatus.PENDING_REVIEW).count(),
        "published_listings": KindnessListing.objects.published().count(),
        "pending_reports": KindnessListingReport.objects.filter(status=ReportStatus.PENDING).count(),
        "active_duplicate_candidates": KindnessDuplicateCandidate.objects.filter(status=DuplicateStatus.ACTIVE).count(),
        "contact_reveals_total": KindnessContactReveal.objects.count(),
    }


def _tabyin_summary() -> dict[str, int]:
    """Return Tabyin content/submission counters."""
    from apps.tabyin.choices import ContentOrigin, SubmissionStatus
    from apps.tabyin.models import TabyinContent

    return {
        "active_contents": TabyinContent.objects.count(),
        "pending_user_submissions": TabyinContent.all_objects.filter(origin=ContentOrigin.USER_SUBMITTED, submission_status=SubmissionStatus.PENDING_REVIEW).count(),
        "rejected_user_submissions": TabyinContent.all_objects.filter(origin=ContentOrigin.USER_SUBMITTED, submission_status=SubmissionStatus.REJECTED).count(),
        "deleted_in_source": TabyinContent.all_objects.filter(is_deleted_in_source=True).count(),
    }


def _public_reports_summary() -> dict[str, int]:
    """Return public report counters."""
    from apps.public_reports.choices import ReportStatus
    from apps.public_reports.models import Report

    return {
        "pending_reports": Report.objects.filter(status=ReportStatus.PENDING).count(),
        "reviewing_reports": Report.objects.filter(status=ReportStatus.REVIEWING).count(),
        "approved_reports": Report.objects.filter(status=ReportStatus.APPROVED).count(),
        "rejected_reports": Report.objects.filter(status=ReportStatus.REJECTED).count(),
    }


def _r4j_summary() -> dict[str, int]:
    """Return R4J moderation and bounty counters."""
    from apps.r4j.choices import BountyStatus, ReportStatus
    from apps.r4j.models import R4JBounty, R4JCriminal, R4JReport

    return {
        "published_criminals": R4JCriminal.objects.filter(is_published=True).count(),
        "pending_reports": R4JReport.objects.filter(status=ReportStatus.PENDING).count(),
        "cancel_requested_reports": R4JReport.objects.filter(status=ReportStatus.CANCEL_REQUESTED).count(),
        "active_bounties": R4JBounty.objects.filter(status=BountyStatus.ACTIVE).count(),
    }


def _madadkar_summary() -> dict[str, int]:
    """Return Madadkar campaign/payment counters."""
    from apps.madadkar.choices import CampaignStatus, PaymentStatus
    from apps.madadkar.models import Campaign, Payment, PaymentReconciliationBatch

    return {
        "published_campaigns": Campaign.objects.filter(status=CampaignStatus.PUBLISHED).count(),
        "completed_campaigns": Campaign.objects.filter(status=CampaignStatus.COMPLETED).count(),
        "pending_payments": Payment.objects.filter(status=PaymentStatus.PENDING).count(),
        "failed_payments": Payment.objects.filter(status=PaymentStatus.FAILED).count(),
        "successful_payments": Payment.objects.filter(status=PaymentStatus.SUCCESS).count(),
        "reconciliation_batches": PaymentReconciliationBatch.objects.count(),
        "reconciliation_mismatches": PaymentReconciliationBatch.objects.aggregate(total=Sum("mismatch_count"))["total"] or 0,
    }


def _lms_summary() -> dict[str, int]:
    """Return LMS learning/certificate counters."""
    from apps.lms.choices import CertificateStatus, CourseStatus, EnrollmentStatus
    from apps.lms.models import Certificate, Course, Enrollment

    return {
        "published_courses": Course.objects.filter(status=CourseStatus.PUBLISHED).count(),
        "active_enrollments": Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE).count(),
        "completed_enrollments": Enrollment.objects.filter(status=EnrollmentStatus.COMPLETED).count(),
        "issued_certificates": Certificate.objects.filter(status=CertificateStatus.ISSUED).count(),
        "revoked_certificates": Certificate.objects.filter(status=CertificateStatus.REVOKED).count(),
    }


def _notifications_summary() -> dict[str, int]:
    """Return notification engine counters."""
    from apps.notifications.choices import NotificationDeliveryStatus, NotificationEventStatus
    from apps.notifications.models import NotificationDelivery, NotificationEvent

    return {
        "pending_events": NotificationEvent.objects.filter(status=NotificationEventStatus.PENDING).count(),
        "failed_events": NotificationEvent.objects.filter(status=NotificationEventStatus.FAILED).count(),
        "pending_deliveries": NotificationDelivery.objects.filter(status=NotificationDeliveryStatus.PENDING).count(),
        "failed_deliveries": NotificationDelivery.objects.filter(status=NotificationDeliveryStatus.FAILED).count(),
        "unread_deliveries": NotificationDelivery.objects.exclude(status=NotificationDeliveryStatus.READ).count(),
    }


def _activity_summary() -> dict[str, int]:
    """Return recent activity counters."""
    from apps.activity.models import UserActivity

    since = timezone.now() - timezone.timedelta(days=1)
    return {
        "total_activities": UserActivity.objects.count(),
        "activities_last_24h": UserActivity.objects.filter(created_at__gte=since).count(),
    }


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
        "checks": {name: {"status": value.get("status"), "latency_ms": value.get("latency_ms")} for name, value in checks.items()},
    }
