"""
Service Layer — business logic گزارشات مردمی.

این فایل تنها مرجع business logic در app گزارشات مردمی است.
تمام عملیات‌هایی که داده را تغییر می‌دهند از اینجا عبور می‌کنند.

اصول طراحی:
- service هرگز request نمی‌گیرد — فقط primitive data.
- IP و metadata در view extract شده و به‌صورت آرگومان پاس داده می‌شود.
- تمام mutations در transaction.atomic هستند.
- structured logging در تمام عملیات‌ها رعایت می‌شود.
"""

from __future__ import annotations

import logging

from django.db import transaction

from .choices import ReportStatus
from .models import Report, ReportAttachment, ReportSubject

logger = logging.getLogger("apps.public_reports")


# ============================================================
# Subject Services
# ============================================================


@transaction.atomic
def create_subject(
    *,
    title: str,
    description: str = "",
    order: int = 0,
) -> ReportSubject:
    """ساخت موضوع گزارش جدید."""
    subject = ReportSubject.objects.create(
        title=title,
        description=description,
        order=order,
    )

    logger.info(
        "Report subject created subject_id=%s title=%s",
        subject.pk,
        subject.title,
    )

    return subject


@transaction.atomic
def update_subject(
    *,
    subject: ReportSubject,
    title: str | None = None,
    description: str | None = None,
    order: int | None = None,
    is_active: bool | None = None,
) -> ReportSubject:
    """ویرایش فیلدهای موضوع گزارش — فقط فیلدهای ارسالی بروزرسانی می‌شوند."""
    update_fields: list[str] = ["updated_at"]

    if title is not None:
        subject.title = title
        update_fields.append("title")

    if description is not None:
        subject.description = description
        update_fields.append("description")

    if order is not None:
        subject.order = order
        update_fields.append("order")

    if is_active is not None:
        subject.is_active = is_active
        update_fields.append("is_active")

    subject.save(update_fields=update_fields)

    logger.info(
        "Report subject updated subject_id=%s fields=%s",
        subject.pk,
        update_fields,
    )

    return subject


@transaction.atomic
def delete_subject(*, subject: ReportSubject) -> None:
    """Soft delete موضوع — فقط غیرفعال می‌شود."""
    subject.soft_delete()

    logger.info(
        "Report subject soft-deleted subject_id=%s title=%s",
        subject.pk,
        subject.title,
    )


# ============================================================
# Report Services
# ============================================================


@transaction.atomic
def create_report(
    *,
    full_name: str,
    subject: ReportSubject,
    description: str,
    phone_number: str | None = None,
    submitter_ip: str | None = None,
    attachments: list | None = None,
) -> Report:
    """
    ثبت گزارش مردمی جدید.

    Note:
    - ``submitter_ip`` باید توسط view از request extract شود.
    - service هرگز مستقیم به request دسترسی ندارد.
    """
    report = Report.objects.create(
        full_name=full_name,
        phone_number=phone_number,
        subject=subject,
        description=description,
        submitter_ip=submitter_ip,
    )

    if attachments:
        ReportAttachment.objects.bulk_create(
            [ReportAttachment(report=report, image=image) for image in attachments],
        )

    logger.info(
        "Report created report_id=%s subject_id=%s ip=%s attachments=%d",
        report.pk,
        subject.pk,
        submitter_ip,
        len(attachments) if attachments else 0,
    )

    return report


@transaction.atomic
def update_report_status(
    *,
    report: Report,
    status: str,
    admin_note: str = "",
) -> Report:
    """
    تغییر وضعیت گزارش توسط ادمین.

    اعتبارسنجی مقدار status در serializer انجام شده؛
    اینجا فقط یک defensive check وجود دارد.
    """
    if status not in ReportStatus.values:
        raise ValueError("وضعیت نامعتبر است.")

    old_status = report.status
    report.status = status

    if admin_note:
        report.admin_note = admin_note

    report.save(update_fields=["status", "admin_note", "updated_at"])

    logger.info(
        "Report status changed report_id=%s old_status=%s new_status=%s",
        report.pk,
        old_status,
        status,
    )

    return report
