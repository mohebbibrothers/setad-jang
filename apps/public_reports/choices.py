"""
Enumeration choices for public report workflows.
"""

from django.db import models


class ReportStatus(models.TextChoices):
    """State machine statuses for public reports."""

    PENDING = "pending", "در انتظار بررسی"
    REVIEWING = "reviewing", "در حال بررسی"
    APPROVED = "approved", "تأیید شده"
    REJECTED = "rejected", "رد شده"


REPORT_ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    ReportStatus.PENDING: frozenset(
        [ReportStatus.PENDING, ReportStatus.REVIEWING, ReportStatus.APPROVED, ReportStatus.REJECTED]
    ),
    ReportStatus.REVIEWING: frozenset(
        [ReportStatus.PENDING, ReportStatus.REVIEWING, ReportStatus.APPROVED, ReportStatus.REJECTED]
    ),
    ReportStatus.APPROVED: frozenset([ReportStatus.APPROVED]),
    ReportStatus.REJECTED: frozenset([ReportStatus.REJECTED]),
}
