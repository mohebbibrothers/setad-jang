"""
Enumeration choices for public report workflows.
"""

from django.db import models


class ReportStatus(models.TextChoices):
    """ReportStatus implementation for the public_reports application."""
    PENDING = "pending", "در انتظار بررسی"
    REVIEWING = "reviewing", "در حال بررسی"
    APPROVED = "approved", "تأیید شده"
    REJECTED = "rejected", "رد شده"
