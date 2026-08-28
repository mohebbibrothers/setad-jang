"""Excel export helpers for Support Desk admin reporting.

خروجی‌ها جریانی تولید می‌شوند (``StreamingExcelSheet``): هر ردیف بلافاصله
روی دیسک نوشته می‌شود و queryset با ``iterator()`` پیمایش می‌شود، پس مصرف
حافظه مستقل از تعداد تیکت‌ها یا پیام‌ها ثابت می‌ماند. جدول پیام‌ها به‌ویژه
حساس است چون ستون «متن» می‌تواند بسیار حجیم باشد.
"""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO

from django.utils import timezone

from apps.core.excel import ExcelColumn, ExcelTheme, StreamingExcelSheet, stream_rows
from apps.support_desk.models import SupportTicket, SupportTicketMessage, SupportTicketSatisfaction

_THEME = ExcelTheme(header_color="4B2E83", summary_color="EFE9FF")

_TICKET_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شماره تیکت", 20, "text"),
    ExcelColumn("موضوع", 36, "text"),
    ExcelColumn("مالک", 28, "text"),
    ExcelColumn("دپارتمان", 24, "text"),
    ExcelColumn("دسته", 24, "text"),
    ExcelColumn("نوع", 22, "text"),
    ExcelColumn("وضعیت", 18, "text"),
    ExcelColumn("اولویت", 16, "text"),
    ExcelColumn("شدت", 16, "text"),
    ExcelColumn("مسئول", 28, "text"),
    ExcelColumn("SLA نقض شده؟", 16, "center"),
    ExcelColumn("تعداد پیام", 14, "int"),
    ExcelColumn("تعداد ضمیمه", 14, "int"),
    ExcelColumn("امتیاز رضایت", 14, "center"),
    ExcelColumn("آخرین فعالیت", 24, "text"),
    ExcelColumn("تاریخ ایجاد", 24, "text"),
]

_MESSAGE_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شماره تیکت", 20, "text"),
    ExcelColumn("نوع پیام", 22, "text"),
    ExcelColumn("نویسنده", 28, "text"),
    ExcelColumn("داخلی؟", 12, "center"),
    ExcelColumn("متن", 70, "text"),
    ExcelColumn("زمان ایجاد", 24, "text"),
]

_SLA_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شماره تیکت", 20, "text"),
    ExcelColumn("وضعیت", 18, "text"),
    ExcelColumn("سیاست SLA", 28, "text"),
    ExcelColumn("اولین پاسخ تا", 24, "text"),
    ExcelColumn("حل تا", 24, "text"),
    ExcelColumn("نقض در", 24, "text"),
    ExcelColumn("ثانیه توقف", 18, "int"),
    ExcelColumn("ارجاع فوری", 16, "center"),
]

_CSAT_COLUMNS: list[ExcelColumn] = [
    ExcelColumn("شماره تیکت", 20, "text"),
    ExcelColumn("کاربر", 28, "text"),
    ExcelColumn("امتیاز", 12, "center"),
    ExcelColumn("نظر", 60, "text"),
    ExcelColumn("زمان ثبت", 24, "text"),
]


def build_tickets_workbook(*, tickets: Iterable[SupportTicket]) -> BytesIO:
    """Build an RTL Excel workbook for support ticket queue/export."""
    sheet = StreamingExcelSheet(
        title="تیکت‌ها", columns=_TICKET_COLUMNS, auto_filter=True, theme=_THEME
    )

    total_messages = 0
    breached = 0
    for ticket in stream_rows(tickets):
        total_messages += ticket.message_count
        breached += 1 if ticket.sla_breached_at else 0
        sheet.append(
            [
                ticket.ticket_number,
                ticket.subject,
                _display_user(ticket.owner),
                ticket.department.title,
                ticket.category.title,
                ticket.ticket_type.title,
                ticket.get_status_display(),
                ticket.get_priority_display(),
                ticket.get_severity_display(),
                _display_user(ticket.assigned_to) if ticket.assigned_to else "",
                "بله" if ticket.sla_breached_at else "خیر",
                ticket.message_count,
                ticket.attachment_count,
                ticket.satisfaction_rating_snapshot or "",
                _format_dt(ticket.last_activity_at),
                _format_dt(ticket.created_at),
            ],
        )

    sheet.append_summary(
        ["جمع", "", "", "", "", "", "", "", "", "", breached, total_messages, "", "", "", ""],
    )
    return sheet.save()


def build_messages_workbook(*, messages: Iterable[SupportTicketMessage]) -> BytesIO:
    """Build an RTL Excel workbook for ticket timeline messages."""
    sheet = StreamingExcelSheet(
        title="پیام‌ها", columns=_MESSAGE_COLUMNS, auto_filter=True, theme=_THEME
    )
    for message in stream_rows(messages):
        sheet.append(
            [
                message.ticket.ticket_number,
                message.get_message_type_display(),
                _display_user(message.author),
                "بله" if message.is_internal else "خیر",
                message.body,
                _format_dt(message.created_at),
            ],
        )
    return sheet.save()


def build_sla_workbook(*, tickets: Iterable[SupportTicket]) -> BytesIO:
    """Build an RTL Excel workbook for SLA breaches and deadlines."""
    sheet = StreamingExcelSheet(title="SLA", columns=_SLA_COLUMNS, auto_filter=True, theme=_THEME)
    for ticket in stream_rows(tickets):
        sheet.append(
            [
                ticket.ticket_number,
                ticket.get_status_display(),
                ticket.applied_sla_policy.title if ticket.applied_sla_policy else "",
                _format_dt(ticket.first_response_due_at),
                _format_dt(ticket.resolution_due_at),
                _format_dt(ticket.sla_breached_at),
                ticket.sla_total_paused_seconds,
                "بله" if ticket.escalated_at else "خیر",
            ],
        )
    return sheet.save()


def build_csat_workbook(*, ratings: Iterable[SupportTicketSatisfaction]) -> BytesIO:
    """Build an RTL Excel workbook for CSAT ratings."""
    sheet = StreamingExcelSheet(
        title="رضایت‌سنجی", columns=_CSAT_COLUMNS, auto_filter=True, theme=_THEME
    )
    total = 0
    count = 0
    for rating in stream_rows(ratings):
        total += rating.rating
        count += 1
        sheet.append(
            [
                rating.ticket.ticket_number,
                _display_user(rating.user),
                rating.rating,
                rating.comment,
                _format_dt(rating.created_at),
            ],
        )
    sheet.append_summary(["میانگین", "", round(total / count, 2) if count else 0, "", ""])
    return sheet.save()


def build_support_export_filename(*, export_type: str) -> str:
    """Build deterministic support export filename."""
    return f"support-{export_type}-{timezone.now():%Y%m%d}.xlsx"


def _format_dt(value) -> str:
    """Format datetime for spreadsheet cells."""
    if value is None:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


def _display_user(user) -> str:
    """Return safe user display string."""
    if user is None:
        return ""
    return getattr(user, "full_name", "") or getattr(user, "email", "") or str(user)
