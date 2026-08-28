"""
Custom throttling scopes for public report submission endpoints.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.core.throttling import ClientIPRateThrottle


class ReportCreateAnonThrottle(AnonRateThrottle):
    """ReportCreateAnonThrottle implementation for the public_reports application."""

    scope = "report_create_anon"


class ReportCreateUserThrottle(UserRateThrottle):
    """ReportCreateUserThrottle implementation for the public_reports application."""

    scope = "report_create_user"


class ReportSubjectListThrottle(ClientIPRateThrottle):
    """
    Throttle اختصاصی لیست موضوعات گزارش (یافتهٔ ممیزی ۵.۱).

    لیست با cache پشت است و ریسک کمی دارد، ولی طبق انضباط پروژه هر
    endpoint عمومی باید scope اختصاصی داشته باشد نه تکیه بر پیش‌فرض.
    کلید per-IP و مستقل از احراز هویت است.
    """

    scope = "public_report_subjects"
