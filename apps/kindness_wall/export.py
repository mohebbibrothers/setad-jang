"""Excel export helpers for Kindness Wall admin analytics.

خروجی‌ها با ``StreamingExcelSheet`` تولید می‌شوند: هر ردیف بلافاصله روی
دیسک نوشته می‌شود و queryset با ``iterator()`` پیمایش می‌شود، پس مصرف حافظه
مستقل از تعداد آگهی‌ها ثابت می‌ماند. نسخهٔ قبلی کل شبکهٔ سلول‌ها را در حافظه
نگه می‌داشت و سپس یک پاس دوم روی همهٔ سلول‌ها برای استایل‌دهی می‌زد.
"""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO

from django.utils import timezone

from apps.core.excel import ExcelColumn, ExcelTheme, StreamingExcelSheet, stream_rows
from apps.kindness_wall.models import KindnessListing, KindnessListingReport

_THEME = ExcelTheme(header_color="7A277A", summary_color="F2EAF2")

_LISTING_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شناسه", 12, "int"),
    ExcelColumn("نوع", 20, "text"),
    ExcelColumn("وضعیت", 18, "text"),
    ExcelColumn("عنوان", 34, "text"),
    ExcelColumn("دسته‌بندی", 24, "text"),
    ExcelColumn("استان", 16, "text"),
    ExcelColumn("شهر", 16, "text"),
    ExcelColumn("نام صاحب آگهی", 24, "text"),
    ExcelColumn("شماره تماس Snapshot", 24, "text"),
    ExcelColumn("بازدید", 14, "int"),
    ExcelColumn("نمایش شماره", 14, "int"),
    ExcelColumn("ذخیره", 12, "int"),
    ExcelColumn("گزارش", 12, "int"),
    ExcelColumn("تاریخ انتشار", 22, "text"),
    ExcelColumn("تاریخ انقضا", 22, "text"),
    ExcelColumn("تاریخ ایجاد", 22, "text"),
]

_REPORT_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شناسه گزارش", 14, "int"),
    ExcelColumn("شناسه آگهی", 14, "int"),
    ExcelColumn("عنوان آگهی", 34, "text"),
    ExcelColumn("دلیل", 22, "text"),
    ExcelColumn("وضعیت", 18, "text"),
    ExcelColumn("توضیحات کاربر", 42, "text"),
    ExcelColumn("یادداشت ادمین", 42, "text"),
    ExcelColumn("گزارش‌دهنده", 24, "text"),
    ExcelColumn("بررسی‌کننده", 24, "text"),
    ExcelColumn("تاریخ ثبت", 22, "text"),
    ExcelColumn("تاریخ بررسی", 22, "text"),
]


def build_listings_workbook(*, listings: Iterable[KindnessListing]) -> BytesIO:
    """Build an RTL Excel workbook for Kindness Wall listings."""
    sheet = StreamingExcelSheet(
        title="آگهی‌ها",
        columns=_LISTING_COLUMNS,
        auto_filter=True,
        theme=_THEME,
    )

    total_views = 0
    total_reveals = 0
    for listing in stream_rows(listings):
        total_views += listing.view_count
        total_reveals += listing.contact_reveal_count
        sheet.append(
            [
                listing.pk,
                listing.get_listing_type_display(),
                listing.get_status_display(),
                listing.title,
                listing.category.title,
                listing.province,
                listing.city,
                listing.owner_full_name_snapshot,
                listing.contact_phone_snapshot,
                listing.view_count,
                listing.contact_reveal_count,
                listing.bookmark_count,
                listing.report_count,
                _format_dt(listing.published_at),
                _format_dt(listing.expires_at),
                _format_dt(listing.created_at),
            ],
        )

    sheet.append_summary(
        ["جمع", "", "", "", "", "", "", "", "", total_views, total_reveals, "", "", "", "", ""],
    )
    return sheet.save()


def build_reports_workbook(*, reports: Iterable[KindnessListingReport]) -> BytesIO:
    """Build an RTL Excel workbook for Kindness Wall report moderation."""
    sheet = StreamingExcelSheet(
        title="گزارش‌ها",
        columns=_REPORT_COLUMNS,
        auto_filter=True,
        theme=_THEME,
    )

    for report in stream_rows(reports):
        sheet.append(
            [
                report.pk,
                report.listing_id,
                report.listing.title,
                report.get_reason_display(),
                report.get_status_display(),
                report.description,
                report.admin_note,
                getattr(report.reported_by, "full_name", "") or str(report.reported_by),
                getattr(report.reviewed_by, "full_name", "") if report.reviewed_by else "",
                _format_dt(report.created_at),
                _format_dt(report.reviewed_at),
            ],
        )

    return sheet.save()


def build_kindness_export_filename(*, export_type: str) -> str:
    """Build deterministic Kindness Wall export filenames."""
    date_part = timezone.now().strftime("%Y%m%d")
    return f"kindness-wall-{export_type}-{date_part}.xlsx"


def _format_dt(value) -> str:
    """Format datetime values for Excel cells."""
    if value is None:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
