"""خروجی Excel پنل ادمین دیوار مهربانی.

دو شیت: آگهی‌ها (بررسی محتوا/کیفیت) و اعلام‌های آمادگی (تریاج داوطلبان).
ردیف‌ها stream می‌شوند تا حافظه با رشد جدول ثابت بماند؛ هیچ اطلاعات تماس
در شیت اعلام‌ها نیست (حریم خصوصی داوطلب).
"""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO

from django.utils import timezone

from apps.core.excel import ExcelColumn, ExcelTheme, StreamingExcelSheet, stream_rows
from apps.kindness_wall.choices import ListingStatus, OfferStatus
from apps.kindness_wall.models import KindnessListing, KindnessOffer

_THEME = ExcelTheme(header_color="7A277A", summary_color="F2EAF2")

_LISTING_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شناسه", 10, "int"),
    ExcelColumn("وضعیت", 16, "text"),
    ExcelColumn("عنوان", 34, "text"),
    ExcelColumn("دسته‌بندی", 22, "text"),
    ExcelColumn("فوریت", 12, "text"),
    ExcelColumn("تعداد", 10, "int"),
    ExcelColumn("واحد", 12, "text"),
    ExcelColumn("استان", 14, "text"),
    ExcelColumn("شهر", 14, "text"),
    ExcelColumn("صاحب آگهی", 22, "text"),
    ExcelColumn("راه‌های تماس", 30, "text"),
    ExcelColumn("بازدید", 10, "int"),
    ExcelColumn("تمدید", 10, "int"),
    ExcelColumn("تاریخ انتشار", 20, "text"),
    ExcelColumn("تاریخ انقضا", 20, "text"),
    ExcelColumn("تاریخ برطرف‌شدن", 20, "text"),
]

_OFFER_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شناسه", 10, "int"),
    ExcelColumn("آگهی", 34, "text"),
    ExcelColumn("وضعیت", 16, "text"),
    ExcelColumn("پیام داوطلب", 42, "text"),
    ExcelColumn("کاربر", 24, "text"),
    ExcelColumn("یادداشت ادمین", 30, "text"),
    ExcelColumn("تاریخ ثبت", 20, "text"),
    ExcelColumn("تاریخ بررسی", 20, "text"),
]


def _format_dt(value) -> str:
    """فرمت تاریخ/ساعت محلی برای سلول؛ خالی برای None."""
    if value is None:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


def build_listings_workbook(*, listings: Iterable[KindnessListing]) -> BytesIO:
    """شیت آگهی‌ها با شمارش وضعیت‌ها در ردیف خلاصه."""
    sheet = StreamingExcelSheet(
        title="آگهی‌ها",
        columns=_LISTING_COLUMNS,
        auto_filter=True,
        theme=_THEME,
    )
    total = 0
    fulfilled = 0
    for listing in stream_rows(listings):
        total += 1
        fulfilled += 1 if listing.status == ListingStatus.FULFILLED else 0
        channels = "، ".join(
            f"{label}={getattr(listing, field)}"
            for field, _code, label, _link in listing.channel_fields()
            if (getattr(listing, field) or "").strip()
        )
        sheet.append(
            [
                listing.pk,
                listing.get_status_display(),
                listing.title,
                listing.category.title if listing.category_id else "",
                listing.get_urgency_display(),
                listing.quantity,
                listing.unit,
                listing.province,
                listing.city,
                listing.beneficiary_name or "—",
                channels or "—",
                listing.view_count,
                listing.renew_count,
                _format_dt(listing.published_at),
                _format_dt(listing.expires_at),
                _format_dt(listing.fulfilled_at),
            ],
        )
    sheet.append_summary(
        [
            "جمع",
            f"کل {total}",
            f"برطرف‌شده {fulfilled}",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
    )
    return sheet.save()


def build_offers_workbook(*, offers: Iterable[KindnessOffer]) -> BytesIO:
    """شیت اعلام‌های آمادگی برای تریاج."""
    sheet = StreamingExcelSheet(
        title="اعلام آمادگی‌ها",
        columns=_OFFER_COLUMNS,
        auto_filter=True,
        theme=_THEME,
    )
    open_count = 0
    for offer in stream_rows(offers):
        open_count += 1 if offer.status == OfferStatus.NEW else 0
        sheet.append(
            [
                offer.pk,
                offer.listing.title,
                offer.get_status_display(),
                offer.message,
                getattr(offer.user, "full_name", "") or str(offer.user),
                offer.admin_note,
                _format_dt(offer.created_at),
                _format_dt(offer.handled_at),
            ],
        )
    sheet.append_summary([f"باز: {open_count}", "", "", "", "", "", "", ""])
    return sheet.save()


def build_kindness_export_filename(*, export_type: str) -> str:
    """نام فایل خروجی با تاریخ محلی — الگوی stable بقیهٔ اپ‌ها."""
    date_part = timezone.now().strftime("%Y%m%d")
    return f"kindness-wall-{export_type}-{date_part}.xlsx"
