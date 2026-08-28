"""
Excel export engine اپ مددکار.

این ماژول یک فایل Excel حرفه‌ای برای گزارش‌گیری از پرداخت‌های یک حرکت
تولید می‌کند.

ویژگی‌ها:
- RTL alignment (راست به چپ — مناسب فارسی)
- Styled headers (پس‌زمینه، فونت bold، border، center)
- Summary row در پایین (مجموع سهم‌ها، مجموع مبلغ، تعداد مشارکت‌کنندگان)
- فرمت‌بندی اعداد با جداکننده هزارگان
- فرمت‌بندی تاریخ بر اساس timezone پروژه
- Auto-width برای ستون‌ها (با محاسبه طول محتوا)
- خروجی به‌صورت BytesIO که قابل ارسال به HttpResponse است
- نام‌گذاری sheet با عنوان حرکت (sanitize شده)

اصول طراحی:
- هیچ DB write در این ماژول انجام نمی‌شود — فقط read.
- نوشتن **جریانی** است: ردیف‌ها با ``StreamingExcelSheet`` تک‌به‌تک روی
  دیسک نوشته می‌شوند و queryset با ``iterator()`` پیمایش می‌شود، پس مصرف
  حافظه مستقل از تعداد مشارکت‌کنندگان ثابت می‌ماند.
- styling در ``apps.core.excel`` متمرکز شده تا بین همهٔ exportها مشترک باشد.
"""

from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.core.excel import ExcelColumn, ExcelTheme, StreamingExcelSheet, localize_for_excel

if TYPE_CHECKING:
    from apps.madadkar.models import Campaign


_THEME = ExcelTheme(header_color="1976D2", summary_color="E3F2FD")

_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("ردیف", 8, "int"),
    ExcelColumn("نام کاربر", 28, "text"),
    ExcelColumn("ایمیل", 32, "text"),
    ExcelColumn("شماره موبایل", 18, "text"),
    ExcelColumn("تعداد سهم", 14, "int"),
    ExcelColumn("قیمت سهم (تومان)", 22, "int"),
    ExcelColumn("مبلغ کل (تومان)", 22, "int"),
    ExcelColumn("کد رهگیری درگاه", 38, "text"),
    ExcelColumn("شناسه مرجع پرداخت", 28, "text"),
    ExcelColumn("نام درگاه", 14, "text"),
    ExcelColumn("تاریخ پرداخت", 22, "date"),
]

#: اندازهٔ دستهٔ خواندن از دیتابیس. با ``iterator`` باعث می‌شود درایور فقط
#: همین تعداد ردیف را در لحظه در حافظه نگه دارد.
_DB_CHUNK_SIZE = 2_000


# ===========================================================================
# Helpers
# ===========================================================================

def _sanitize_sheet_name(name: str, max_length: int = 31) -> str:
    r"""
    پاکسازی نام sheet برای Excel.

    Excel محدودیت‌هایی برای نام sheet دارد:
    - حداکثر 31 کاراکتر
    - کاراکترهای ممنوع: : \ / ? * [ ]
    """
    cleaned = re.sub(r"[:\\/?*\[\]]", "-", name)
    cleaned = cleaned.strip()[:max_length]
    return cleaned or "Sheet1"


def _get_user_display_name(user) -> str:
    """نام نمایشی کاربر — fallback chain تا یک مقدار معتبر."""
    full_name = ""
    if hasattr(user, "get_full_name"):
        full_name = (user.get_full_name() or "").strip()
    if full_name:
        return full_name
    if hasattr(user, "first_name") and hasattr(user, "last_name"):
        combined = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if combined:
            return combined
    return getattr(user, "email", "") or getattr(user, "username", "") or "—"


def _get_user_mobile(user) -> str:
    """شماره موبایل کاربر — defensive lookup."""
    return (
        getattr(user, "phone_number", "")
        or getattr(user, "mobile", "")
        or "—"
    )


# ===========================================================================
# Main export function
# ===========================================================================

def generate_campaign_participants_excel(*, campaign: Campaign) -> io.BytesIO:
    """
    تولید فایل Excel گزارش پرداخت‌های یک حرکت.

    این تابع تمام Participationهای PAID مربوط به campaign را به Excel
    تبدیل می‌کند. ترتیب: بزرگ‌ترین مبلغ ابتدا (descending by total_amount)،
    سپس بر اساس paid_at descending.

    Args:
        campaign: حرکتی که می‌خواهیم پرداخت‌هایش export شود.

    Returns:
        BytesIO حاوی فایل xlsx آماده برای ارسال در HttpResponse.

    Raises:
        ExcelExportTooLargeError: اگر تعداد ردیف‌ها از سقف ``EXPORT_MAX_ROWS``
            عبور کند.

    نکات معماری
    ------------
    - importهای selectors داخل بدنه انجام می‌شود تا circular import پیش نیاید.
    - نوشتن جریانی است: هر ردیف بلافاصله روی دیسک می‌رود و queryset با
      ``iterator(chunk_size=...)`` پیمایش می‌شود. نسخهٔ قبلی کل workbook را
      به‌صورت شیء در حافظه نگه می‌داشت و برای یک حرکت با ده‌ها هزار
      مشارکت‌کننده می‌توانست چند صد مگابایت در یک worker گانیکورن مصرف کند
      و آن را با OOM از پا دربیاورد.
    - ردیف خلاصه دیگر سلول ادغام‌شده ندارد (در حالت write-only ممکن نیست) و
      برچسب در ستون اول نوشته می‌شود.
    """
    # late import — جلوگیری از circular
    from apps.madadkar.selectors import get_campaign_participants_for_export

    participations = get_campaign_participants_for_export(campaign=campaign)

    sheet = StreamingExcelSheet(
        title=_sanitize_sheet_name(campaign.title),
        columns=_COLUMNS,
        theme=_THEME,
    )

    total_shares = 0
    total_amount = 0
    unique_users: set[int] = set()

    for index, participation in enumerate(participations.iterator(chunk_size=_DB_CHUNK_SIZE), start=1):
        user = participation.user
        payment = participation.payment

        sheet.append(
            [
                index,
                _get_user_display_name(user),
                getattr(user, "email", "") or "—",
                _get_user_mobile(user),
                participation.share_count,
                participation.share_price_snapshot,
                participation.total_amount,
                payment.authority if payment else "—",
                (payment.ref_id if payment and payment.ref_id else "—"),
                (payment.gateway_name if payment else "—"),
                localize_for_excel(participation.paid_at),
            ],
        )

        total_shares += participation.share_count
        total_amount += participation.total_amount
        unique_users.add(user.pk)

    sheet.append_summary(
        [
            f"مجموع — {len(unique_users):,} مشارکت‌کننده یکتا",
            None,
            None,
            None,
            total_shares,
            None,
            total_amount,
            None,
            None,
            None,
            None,
        ],
    )
    return sheet.save()


def build_excel_filename(*, campaign: Campaign) -> str:
    """
    ساخت نام فایل پیشنهادی برای دانلود.

    فرمت: madadkar-{campaign_id}-{slugified-title}-{YYYYMMDD-HHMMSS}.xlsx
    """
    now = timezone.localtime(timezone.now()).strftime("%Y%m%d-%H%M%S")
    safe_title = re.sub(r"[^\w-]+", "-", campaign.slug)[:60]
    return f"madadkar-{campaign.pk}-{safe_title}-{now}.xlsx"
