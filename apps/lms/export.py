"""Excel export helpers for LMS admin analytics.

خروجی جریانی تولید می‌شود (``StreamingExcelSheet``) و queryset با
``iterator()`` پیمایش می‌شود، پس مصرف حافظه مستقل از تعداد ثبت‌نام‌های یک
دوره ثابت می‌ماند. exportها عمداً بیرون از views/services نگه داشته شده‌اند
تا قابل تست و جایگزینی بمانند.
"""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO

from django.utils import timezone

from apps.core.excel import ExcelColumn, ExcelTheme, StreamingExcelSheet, stream_rows
from apps.lms.models import Course, Enrollment

_THEME = ExcelTheme(header_color="277A7E", summary_color="E3F2FD")

_ENROLLMENT_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شناسه ثبت‌نام", 16, "int"),
    ExcelColumn("نام کامل", 28, "text"),
    ExcelColumn("ایمیل", 32, "text"),
    ExcelColumn("وضعیت", 18, "text"),
    ExcelColumn("درصد پیشرفت", 18, "decimal"),
    ExcelColumn("ثانیه مشاهده‌شده", 20, "int"),
    ExcelColumn("کد مدرک", 28, "text"),
    ExcelColumn("تاریخ ثبت‌نام", 24, "text"),
    ExcelColumn("تاریخ تکمیل", 24, "text"),
]


def build_course_enrollments_workbook(*, course: Course, enrollments: Iterable[Enrollment]) -> BytesIO:
    """Build an RTL Excel workbook for a course participant report."""
    sheet = StreamingExcelSheet(
        title=course.title,
        columns=_ENROLLMENT_COLUMNS,
        theme=_THEME,
    )

    for enrollment in stream_rows(enrollments):
        user = enrollment.user
        certificate = getattr(enrollment, "certificate", None)
        sheet.append(
            [
                enrollment.pk,
                getattr(user, "full_name", "") or str(user),
                getattr(user, "email", "") or "",
                enrollment.get_status_display(),
                float(enrollment.progress_percent or 0),
                enrollment.watched_seconds,
                getattr(certificate, "certificate_code", "") if certificate else "",
                _format_dt(enrollment.enrolled_at),
                _format_dt(enrollment.completed_at),
            ],
        )

    return sheet.save()


def build_course_export_filename(*, course: Course) -> str:
    """Build a deterministic export filename for a course report."""
    date_part = timezone.now().strftime("%Y%m%d")
    return f"lms-course-{course.pk}-participants-{date_part}.xlsx"


def _format_dt(value) -> str:
    """Format datetime values for Excel cells."""
    if value is None:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")

