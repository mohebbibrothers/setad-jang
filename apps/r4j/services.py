"""
Services اپ R4J — business logic.

تمام عملیات mutation از این لایه عبور می‌کنند تا:
- transaction safety تضمین شود
- logging consistent بماند
- audit hooks در یک نقطه centralize شوند
- view از business logic decouple بماند

اصول طراحی:
- هیچ service پارامتر request نمی‌گیرد — فقط primitive data.
- تمام public functions ورودی keyword-only دارند.
- تمام mutationها داخل transaction.atomic هستند.
- type-safe field application از field_applicators استفاده می‌کند.
- bounty operations از select_for_update برای concurrency safety استفاده می‌کنند.
- counterهای denormalized criminal بعد از هر bounty mutation sync می‌شوند.

بخش‌ها:
1. Exceptions
2. Criminal — CRUD
3. Criminal — publish lifecycle
4. Aliases
5. Phones
6. Socials
7. Photos (با primary auto-management)
8. Attachments
9. Field visibility
10. Reports — submit / cancel / review / apply
11. Bounties — set / cancel / approve / reject + counter sync
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .choices import (
    BOUNTY_ACTIVE_STATUSES,
    BountyStatus,
    CriminalAttachmentKind,
    EvidenceCustodyEventType,
    Gender,
    ReportFieldChangeStatus,
    ReportStatus,
    SocialPlatform,
)
from .field_applicators import FieldApplicationError, apply_field_to_criminal
from .models import (
    R4JBounty,
    R4JCriminal,
    R4JCriminalAlias,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JCriminalPhone,
    R4JCriminalPhoto,
    R4JCriminalSocial,
    R4JEvidenceCustodyEvent,
    R4JReport,
    R4JReportAliasSuggestion,
    R4JReportAttachment,
    R4JReportFieldChange,
    R4JReportPhoneSuggestion,
    R4JReportSocialSuggestion,
)
from .validators import validate_bounty_amount

logger = logging.getLogger("apps.r4j")

User = get_user_model()

# ============================================================
# فیلدهای قابل تغییر از طریق report
# ============================================================

#: فقط این فیلدهای مستقیم (scalar) روی R4JCriminal می‌توانند از طریق
#: community report اعمال شوند.
#:
#: نکته: این مقدار باید با REPORTABLE_CRIMINAL_FIELDS در validators.py
#: هم‌راستا باشد. تغییر در یکی باید در دیگری هم اعمال شود.
REPORTABLE_CRIMINAL_FIELDS: frozenset[str] = frozenset(
    {
        "first_name",
        "last_name",
        "national_code",
        "birth_date",
        "gender",
        "country",
        "province",
        "city",
        "description",
        "crimes_summary",
        "other_info",
    }
)


# ============================================================
# Custom service exceptions
# ============================================================


class R4JServiceError(Exception):
    """Base exception برای service layer R4J."""


class CriminalAlreadyPublished(R4JServiceError):
    """تلاش برای انتشار criminal که قبلاً منتشر شده."""


class CriminalAlreadyUnpublished(R4JServiceError):
    """تلاش برای unpublish کردن criminal که قبلاً unpublish است."""


class ReportNotCancelable(R4JServiceError):
    """گزارش در وضعیتی نیست که بتوان آن را cancel کرد."""


class ReportNotReviewable(R4JServiceError):
    """گزارش در وضعیتی نیست که بتوان آن را review کرد."""


class ReportNotInCancelRequested(R4JServiceError):
    """گزارش در وضعیت cancel_requested نیست."""


class InvalidReportableField(R4JServiceError):
    """فیلد ارسال‌شده در report قابل تغییر از این مسیر نیست."""


class InvalidBountyAmount(R4JServiceError):
    """مبلغ bounty نامعتبر است."""


class BountyNotCancelable(R4JServiceError):
    """bounty در وضعیتی نیست که بتوان برای آن درخواست لغو ثبت کرد."""


class BountyNotInCancelRequested(R4JServiceError):
    """bounty در وضعیت cancel_requested نیست."""


class BountyUpdateNotAllowed(R4JServiceError):
    """bounty در وضعیتی نیست که بتوان آن را set/update کرد."""


# ============================================================
# Criminal — CRUD
# ============================================================


@transaction.atomic
def create_criminal(
    *,
    created_by: User,
    first_name: str,
    last_name: str,
    gender: str = Gender.UNKNOWN,
    national_code: str | None = None,
    birth_date: Any = None,
    country: str = "",
    province: str = "",
    city: str = "",
    description: str = "",
    crimes_summary: str = "",
    other_info: str = "",
) -> R4JCriminal:
    """ساخت پروفایل جدید مجرم — همیشه به‌صورت draft (is_published=False)."""
    criminal = R4JCriminal.objects.create(
        created_by=created_by,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        national_code=national_code or None,
        birth_date=birth_date,
        country=country,
        province=province,
        city=city,
        description=description,
        crimes_summary=crimes_summary,
        other_info=other_info,
        is_published=False,
    )

    logger.info(
        "R4J criminal created id=%s slug=%s created_by=%s",
        criminal.pk,
        criminal.slug,
        getattr(created_by, "pk", None),
    )

    return criminal


@transaction.atomic
def update_criminal(*, criminal: R4JCriminal, **fields: Any) -> R4JCriminal:
    """ویرایش فیلدهای editable یک criminal — فقط فیلدهای ارسالی."""
    editable_fields = {
        "first_name",
        "last_name",
        "national_code",
        "birth_date",
        "gender",
        "country",
        "province",
        "city",
        "description",
        "crimes_summary",
        "other_info",
    }

    update_fields: list[str] = ["updated_at"]
    for key, value in fields.items():
        if key in editable_fields and value is not None:
            setattr(criminal, key, value)
            update_fields.append(key)

    if len(update_fields) > 1:
        criminal.save(update_fields=update_fields)
        logger.info(
            "R4J criminal updated id=%s fields=%s",
            criminal.pk,
            sorted(set(update_fields) - {"updated_at"}),
        )

    return criminal


@transaction.atomic
def soft_delete_criminal(*, criminal: R4JCriminal) -> None:
    """soft delete کردن criminal — خودکار unpublish هم می‌شود."""
    criminal.soft_delete()
    logger.info("R4J criminal soft-deleted id=%s", criminal.pk)


# ============================================================
# Criminal — publish lifecycle
# ============================================================


@transaction.atomic
def publish_criminal(*, criminal: R4JCriminal) -> R4JCriminal:
    """انتشار criminal — exception می‌دهد اگر قبلاً منتشر شده باشد."""
    if criminal.is_published:
        raise CriminalAlreadyPublished("این پروفایل قبلاً منتشر شده است.")

    criminal.is_published = True
    criminal.published_at = timezone.now()
    criminal.save(update_fields=["is_published", "published_at", "updated_at"])

    logger.info("R4J criminal published id=%s", criminal.pk)
    return criminal


@transaction.atomic
def unpublish_criminal(*, criminal: R4JCriminal) -> R4JCriminal:
    """خروج از انتشار — exception می‌دهد اگر قبلاً unpublish باشد."""
    if not criminal.is_published:
        raise CriminalAlreadyUnpublished("این پروفایل منتشر نشده است.")

    criminal.is_published = False
    criminal.save(update_fields=["is_published", "updated_at"])

    logger.info("R4J criminal unpublished id=%s", criminal.pk)
    return criminal


# ============================================================
# Aliases
# ============================================================


@transaction.atomic
def add_alias(*, criminal: R4JCriminal, alias: str) -> R4JCriminalAlias:
    """افزودن نام مستعار به criminal."""
    obj = R4JCriminalAlias.objects.create(criminal=criminal, alias=alias)
    logger.info("R4J alias added criminal=%s alias=%s", criminal.pk, alias)
    return obj


@transaction.atomic
def remove_alias(*, alias_obj: R4JCriminalAlias) -> None:
    """حذف یک نام مستعار."""
    pk = alias_obj.pk
    criminal_id = alias_obj.criminal_id
    alias_obj.delete()
    logger.info("R4J alias removed id=%s criminal=%s", pk, criminal_id)


# ============================================================
# Phones
# ============================================================


@transaction.atomic
def add_phone(
    *,
    criminal: R4JCriminal,
    number: str,
    label: str = "",
    is_public: bool = False,
    notes: str = "",
) -> R4JCriminalPhone:
    """افزودن شماره تماس به criminal."""
    obj = R4JCriminalPhone.objects.create(
        criminal=criminal,
        number=number,
        label=label,
        is_public=is_public,
        notes=notes,
    )
    logger.info("R4J phone added criminal=%s phone_id=%s", criminal.pk, obj.pk)
    return obj


@transaction.atomic
def update_phone(*, phone: R4JCriminalPhone, **fields: Any) -> R4JCriminalPhone:
    """ویرایش شماره تماس."""
    editable = {"number", "label", "is_public", "notes"}
    update_fields: list[str] = ["updated_at"]
    for key, value in fields.items():
        if key in editable and value is not None:
            setattr(phone, key, value)
            update_fields.append(key)
    if len(update_fields) > 1:
        phone.save(update_fields=update_fields)
        logger.info("R4J phone updated id=%s", phone.pk)
    return phone


@transaction.atomic
def remove_phone(*, phone: R4JCriminalPhone) -> None:
    """حذف شماره تماس."""
    pk = phone.pk
    criminal_id = phone.criminal_id
    phone.delete()
    logger.info("R4J phone removed id=%s criminal=%s", pk, criminal_id)


# ============================================================
# Socials
# ============================================================


@transaction.atomic
def add_social(
    *,
    criminal: R4JCriminal,
    platform: str,
    handle_or_url: str,
    is_public: bool = True,
) -> R4JCriminalSocial:
    """افزودن حساب شبکه اجتماعی به criminal."""
    if platform not in SocialPlatform.values:
        raise R4JServiceError("پلتفرم نامعتبر است.")

    obj = R4JCriminalSocial.objects.create(
        criminal=criminal,
        platform=platform,
        handle_or_url=handle_or_url,
        is_public=is_public,
    )
    logger.info(
        "R4J social added criminal=%s social_id=%s platform=%s",
        criminal.pk,
        obj.pk,
        platform,
    )
    return obj


@transaction.atomic
def update_social(*, social: R4JCriminalSocial, **fields: Any) -> R4JCriminalSocial:
    """ویرایش شبکه اجتماعی."""
    editable = {"platform", "handle_or_url", "is_public"}
    update_fields: list[str] = ["updated_at"]
    for key, value in fields.items():
        if key in editable and value is not None:
            setattr(social, key, value)
            update_fields.append(key)
    if len(update_fields) > 1:
        social.save(update_fields=update_fields)
        logger.info("R4J social updated id=%s", social.pk)
    return social


@transaction.atomic
def remove_social(*, social: R4JCriminalSocial) -> None:
    """حذف شبکه اجتماعی."""
    pk = social.pk
    criminal_id = social.criminal_id
    social.delete()
    logger.info("R4J social removed id=%s criminal=%s", pk, criminal_id)


# ============================================================
# Photos (با primary auto-management)
# ============================================================


@transaction.atomic
def add_photo(
    *,
    criminal: R4JCriminal,
    image: Any,
    caption: str = "",
    is_primary: bool = False,
    order: int = 0,
) -> R4JCriminalPhoto:
    """افزودن عکس جدید با مدیریت خودکار primary."""
    if is_primary:
        R4JCriminalPhoto.objects.filter(
            criminal=criminal,
            is_primary=True,
        ).update(is_primary=False, updated_at=timezone.now())

    obj = R4JCriminalPhoto.objects.create(
        criminal=criminal,
        image=image,
        caption=caption,
        is_primary=is_primary,
        order=order,
    )
    logger.info(
        "R4J photo added criminal=%s photo_id=%s primary=%s",
        criminal.pk,
        obj.pk,
        is_primary,
    )
    return obj


@transaction.atomic
def set_primary_photo(*, photo: R4JCriminalPhoto) -> R4JCriminalPhoto:
    """تنظیم یک photo به‌عنوان primary — سایرین خودکار demote می‌شوند."""
    R4JCriminalPhoto.objects.filter(
        criminal_id=photo.criminal_id,
        is_primary=True,
    ).exclude(pk=photo.pk).update(is_primary=False, updated_at=timezone.now())

    if not photo.is_primary:
        photo.is_primary = True
        photo.save(update_fields=["is_primary", "updated_at"])
        logger.info("R4J photo set primary id=%s", photo.pk)

    return photo


@transaction.atomic
def remove_photo(*, photo: R4JCriminalPhoto) -> None:
    """حذف photo — اگر primary بود، اولین photo باقی‌مانده auto-promote می‌شود."""
    criminal_id = photo.criminal_id
    was_primary = photo.is_primary
    pk = photo.pk
    photo.delete()
    logger.info("R4J photo removed id=%s criminal=%s", pk, criminal_id)

    if was_primary:
        next_photo = (
            R4JCriminalPhoto.objects.filter(criminal_id=criminal_id)
            .order_by("order", "-created_at")
            .first()
        )
        if next_photo:
            next_photo.is_primary = True
            next_photo.save(update_fields=["is_primary", "updated_at"])
            logger.info(
                "R4J photo auto-promoted id=%s criminal=%s",
                next_photo.pk,
                criminal_id,
            )


# ============================================================
# Attachments
# ============================================================


def _hash_file_field(file_field: Any) -> tuple[str, int]:
    """Compute SHA-256 and byte size for a Django file field without leaking content."""
    digest = hashlib.sha256()
    size = 0
    file_field.open("rb")
    try:
        for chunk in file_field.chunks():
            size += len(chunk)
            digest.update(chunk)
    finally:
        file_field.close()
    return digest.hexdigest(), size


def _create_custody_event(
    *,
    criminal_attachment: R4JCriminalAttachment | None = None,
    report_attachment: R4JReportAttachment | None = None,
    event_type: str,
    actor: User | None = None,
    note: str = "",
    metadata: dict[str, Any] | None = None,
) -> R4JEvidenceCustodyEvent:
    """Create append-only custody event for one evidence attachment."""
    target = criminal_attachment or report_attachment
    return R4JEvidenceCustodyEvent.objects.create(
        criminal_attachment=criminal_attachment,
        report_attachment=report_attachment,
        event_type=event_type,
        actor=actor,
        file_sha256=getattr(target, "file_sha256", "") if target else "",
        note=note,
        metadata=metadata or {},
    )


def _finalize_evidence_hash(*, attachment: Any, actor: User | None) -> None:
    """Persist evidence hash/size and custody events for an attachment."""
    file_hash, file_size = _hash_file_field(attachment.file)
    attachment.file_sha256 = file_hash
    attachment.file_size = file_size
    attachment.save(update_fields=["file_sha256", "file_size", "updated_at"])
    kwargs = (
        {"criminal_attachment": attachment}
        if isinstance(attachment, R4JCriminalAttachment)
        else {"report_attachment": attachment}
    )
    _create_custody_event(
        **kwargs,
        event_type=EvidenceCustodyEventType.UPLOADED,
        actor=actor,
        metadata={"file_size": file_size},
    )
    _create_custody_event(
        **kwargs,
        event_type=EvidenceCustodyEventType.HASHED,
        actor=actor,
        metadata={"sha256": file_hash},
    )


@transaction.atomic
def add_attachment(
    *,
    criminal: R4JCriminal,
    file: Any,
    title: str,
    kind: str = CriminalAttachmentKind.DOCUMENT,
    description: str = "",
    is_public: bool = False,
    uploaded_by: User | None = None,
) -> R4JCriminalAttachment:
    """افزودن سند به پروفایل criminal."""
    obj = R4JCriminalAttachment.objects.create(
        criminal=criminal,
        file=file,
        title=title,
        kind=kind,
        description=description,
        is_public=is_public,
        uploaded_by=uploaded_by,
    )
    _finalize_evidence_hash(attachment=obj, actor=uploaded_by)
    logger.info(
        "R4J attachment added criminal=%s attachment_id=%s kind=%s",
        criminal.pk,
        obj.pk,
        kind,
    )
    return obj


@transaction.atomic
def remove_attachment(*, attachment: R4JCriminalAttachment) -> None:
    """حذف سند."""
    pk = attachment.pk
    criminal_id = attachment.criminal_id
    attachment.delete()
    logger.info("R4J attachment removed id=%s criminal=%s", pk, criminal_id)


# ============================================================
# Field visibility
# ============================================================


@transaction.atomic
def upsert_field_visibility(
    *,
    criminal: R4JCriminal,
    field_name: str,
    is_public: bool,
) -> R4JCriminalFieldVisibility:
    """ساخت یا به‌روزرسانی override نمایش یک فیلد."""
    obj, created = R4JCriminalFieldVisibility.objects.update_or_create(
        criminal=criminal,
        field_name=field_name,
        defaults={"is_public": is_public},
    )
    logger.info(
        "R4J field visibility %s criminal=%s field=%s is_public=%s",
        "created" if created else "updated",
        criminal.pk,
        field_name,
        is_public,
    )
    return obj


# ============================================================
# Reports — submit
# ============================================================


@transaction.atomic
def submit_report(
    *,
    criminal: R4JCriminal,
    submitted_by: User,
    notes: str = "",
    field_changes: list[dict[str, str]],
    attachments: list[Any] | None = None,
    alias_suggestions: list[dict[str, Any]] | None = None,
    phone_suggestions: list[dict[str, Any]] | None = None,
    social_suggestions: list[dict[str, Any]] | None = None,
) -> R4JReport:
    """
    ثبت گزارش community برای تکمیل/اصلاح اطلاعات یک مجرم.

    هر field_change باید دارای field_name و suggested_value باشد.
    فیلدهایی که در REPORTABLE_CRIMINAL_FIELDS نیستند رد می‌شوند.

    Args:
        criminal: مجرمی که گزارش برای اوست.
        submitted_by: کاربر گزارش‌دهنده.
        notes: یادداشت آزاد گزارش‌دهنده.
        field_changes: لیست dict با کلیدهای field_name و suggested_value.
        attachments: لیست فایل‌های ضمیمه (اختیاری).
        alias_suggestions: نام‌های مستعار پیشنهادی.
        phone_suggestions: شماره‌های تماس پیشنهادی.
        social_suggestions: آدرس‌های ارتباطی/شبکه اجتماعی پیشنهادی.

    Raises:
        InvalidReportableField: اگر field_name غیر مجاز ارسال شود.
    """
    for fc in field_changes:
        if fc["field_name"] not in REPORTABLE_CRIMINAL_FIELDS:
            raise InvalidReportableField(
                f"فیلد '{fc['field_name']}' از طریق گزارش قابل تغییر نیست.",
            )

    report = R4JReport.objects.create(
        criminal=criminal,
        submitted_by=submitted_by,
        notes=notes,
        status=ReportStatus.PENDING,
    )

    for fc in field_changes:
        field_name = fc["field_name"]
        current_value = str(getattr(criminal, field_name, "") or "")
        R4JReportFieldChange.objects.create(
            report=report,
            field_name=field_name,
            suggested_value=fc["suggested_value"],
            current_value_snapshot=current_value,
            status=ReportFieldChangeStatus.PENDING,
        )

    for suggestion in alias_suggestions or []:
        R4JReportAliasSuggestion.objects.create(
            report=report,
            alias=suggestion["alias"],
            status=ReportFieldChangeStatus.PENDING,
        )

    for suggestion in phone_suggestions or []:
        R4JReportPhoneSuggestion.objects.create(
            report=report,
            label=suggestion.get("label", ""),
            number=suggestion["number"],
            is_public=suggestion.get("is_public", False),
            notes=suggestion.get("notes", ""),
            status=ReportFieldChangeStatus.PENDING,
        )

    for suggestion in social_suggestions or []:
        R4JReportSocialSuggestion.objects.create(
            report=report,
            platform=suggestion["platform"],
            handle_or_url=suggestion["handle_or_url"],
            is_public=suggestion.get("is_public", True),
            status=ReportFieldChangeStatus.PENDING,
        )

    if attachments:
        for att in attachments:
            report_attachment = R4JReportAttachment.objects.create(
                report=report,
                file=att["file"],
                title=att.get("title", ""),
                kind=att.get("kind", "document"),
            )
            _finalize_evidence_hash(attachment=report_attachment, actor=submitted_by)

    logger.info(
        "R4J report submitted report_id=%s criminal=%s user=%s field_count=%s",
        report.pk,
        criminal.pk,
        submitted_by.pk,
        len(field_changes),
    )

    return report


# ============================================================
# Reports — cancel request (توسط user)
# ============================================================


@transaction.atomic
def request_report_cancel(*, report: R4JReport, user: User) -> R4JReport:
    """
    درخواست لغو گزارش توسط کاربر.

    فقط گزارش‌های با وضعیت PENDING قابل cancel هستند.
    گزارش‌های already reviewed (approved/rejected/canceled) قابل cancel نیستند.

    Args:
        report: گزارش مورد نظر.
        user: کاربر درخواست‌دهنده.

    Raises:
        ReportNotCancelable: اگر وضعیت گزارش اجازه لغو ندهد.
    """
    if report.status != ReportStatus.PENDING:
        raise ReportNotCancelable(
            "فقط گزارش‌هایی که در انتظار بررسی هستند قابل درخواست لغو می‌باشند.",
        )

    report.status = ReportStatus.CANCEL_REQUESTED
    report.cancel_requested_at = timezone.now()
    report.save(update_fields=["status", "cancel_requested_at", "updated_at"])

    logger.info(
        "R4J report cancel requested report_id=%s user=%s",
        report.pk,
        user.pk,
    )

    return report


# ============================================================
# Reports — review (توسط admin)
# ============================================================


def _decision_map(decisions: list[dict[str, Any]] | None, id_key: str) -> dict[int, dict[str, Any]]:
    """Build an id-indexed decision map for report review resources."""
    return {int(item[id_key]): item for item in decisions or [] if id_key in item}


def _apply_alias_suggestion(*, suggestion: R4JReportAliasSuggestion) -> None:
    """Apply an approved alias suggestion idempotently."""
    alias, _ = R4JCriminalAlias.objects.get_or_create(
        criminal=suggestion.report.criminal,
        alias=suggestion.alias.strip(),
    )
    suggestion.applied_alias = alias


def _apply_phone_suggestion(*, suggestion: R4JReportPhoneSuggestion) -> None:
    """Apply an approved phone suggestion by creating a profile phone record."""
    phone = R4JCriminalPhone.objects.create(
        criminal=suggestion.report.criminal,
        label=suggestion.label,
        number=suggestion.number,
        is_public=suggestion.is_public,
        notes=suggestion.notes,
    )
    suggestion.applied_phone = phone


def _apply_social_suggestion(*, suggestion: R4JReportSocialSuggestion) -> None:
    """Apply an approved social suggestion idempotently."""
    social, _ = R4JCriminalSocial.objects.get_or_create(
        criminal=suggestion.report.criminal,
        platform=suggestion.platform,
        handle_or_url=suggestion.handle_or_url,
        defaults={"is_public": suggestion.is_public},
    )
    suggestion.applied_social = social


def _promote_report_attachment(*, attachment: R4JReportAttachment, actor: User) -> None:
    """Promote report evidence into an official criminal attachment without losing custody."""
    criminal_attachment = R4JCriminalAttachment.objects.create(
        criminal=attachment.report.criminal,
        file=attachment.file.name,
        kind=attachment.kind,
        title=attachment.title or f"report-attachment-{attachment.pk}",
        description=f"Promoted from R4J report #{attachment.report_id}",
        is_public=False,
        uploaded_by=actor,
        file_sha256=attachment.file_sha256,
        file_size=attachment.file_size,
    )
    attachment.promoted_criminal_attachment = criminal_attachment
    _create_custody_event(
        criminal_attachment=criminal_attachment,
        event_type=EvidenceCustodyEventType.TRANSFERRED,
        actor=actor,
        metadata={
            "source_report_attachment_id": attachment.pk,
            "source_report_id": attachment.report_id,
        },
    )


def _apply_suggestion_decisions(
    *,
    queryset,
    decisions: list[dict[str, Any]] | None,
    id_key: str,
    apply_callback,
    actor: User,
) -> list[str]:
    """Apply approve/reject decisions for typed suggestion querysets."""
    decisions_map = _decision_map(decisions, id_key)
    final_statuses: list[str] = []
    for suggestion in queryset:
        decision = decisions_map.get(suggestion.pk)
        if decision is None:
            final_statuses.append(suggestion.status)
            continue
        new_status = decision.get("status", ReportFieldChangeStatus.PENDING)
        suggestion.status = new_status
        suggestion.admin_note = decision.get("admin_note", "")
        if new_status == ReportFieldChangeStatus.APPROVED:
            apply_callback(suggestion=suggestion) if id_key != "attachment_id" else apply_callback(
                attachment=suggestion, actor=actor
            )
        suggestion.save()
        final_statuses.append(suggestion.status)
    return final_statuses


@transaction.atomic
def review_report(
    *,
    report: R4JReport,
    reviewed_by: User,
    field_decisions: list[dict[str, Any]],
    alias_decisions: list[dict[str, Any]] | None = None,
    phone_decisions: list[dict[str, Any]] | None = None,
    social_decisions: list[dict[str, Any]] | None = None,
    attachment_decisions: list[dict[str, Any]] | None = None,
    admin_note: str = "",
) -> R4JReport:
    """
    بررسی گزارش توسط ادمین — per-field approve/reject + apply changes.

    این تابع مهم‌ترین عملیات phase R4J.3 است:
    1. هر field_change را بر اساس field_decisions به‌روز می‌کند.
    2. تغییرات approved را با type-safety روی criminal اعمال می‌کند (atomic).
    3. وضعیت نهایی report را بر اساس نتیجه ست می‌کند.

    نکته طراحی:
    - فقط گزارش‌های PENDING قابل review هستند.
    - گزارش‌های CANCEL_REQUESTED باید از مسیر approve/reject cancel برگردند.

    Args:
        report: گزارش مورد بررسی.
        reviewed_by: ادمین بررسی‌کننده.
        field_decisions: لیست dict با کلیدهای:
            - field_change_id (int)
            - status ("approved" | "rejected")
            - admin_note (str, اختیاری)
        admin_note: یادداشت کلی ادمین روی گزارش.

    Raises:
        ReportNotReviewable: اگر وضعیت گزارش PENDING نباشد.

    Returns:
        گزارش به‌روزشده با status نهایی.
    """
    if report.status != ReportStatus.PENDING:
        raise ReportNotReviewable(
            "فقط گزارش‌هایی که در انتظار بررسی هستند قابل review هستند. "
            "برای گزارش‌های در وضعیت درخواست لغو از endpoint مربوطه استفاده کنید.",
        )

    decisions_map: dict[int, dict[str, Any]] = {d["field_change_id"]: d for d in field_decisions}

    field_changes = list(report.field_changes.all())
    approved_changes: list[R4JReportFieldChange] = []

    for fc in field_changes:
        decision = decisions_map.get(fc.pk)
        if decision is None:
            continue

        new_status = decision.get("status", ReportFieldChangeStatus.PENDING)
        fc.status = new_status
        fc.admin_note = decision.get("admin_note", "")
        fc.save(update_fields=["status", "admin_note", "updated_at"])

        if new_status == ReportFieldChangeStatus.APPROVED:
            approved_changes.append(fc)

    if approved_changes:
        _apply_field_changes_to_criminal(
            criminal=report.criminal,
            approved_changes=approved_changes,
        )

    all_statuses = list(
        R4JReportFieldChange.objects.filter(report=report).values_list("status", flat=True),
    )
    all_statuses += _apply_suggestion_decisions(
        queryset=list(report.alias_suggestions.all()),
        decisions=alias_decisions,
        id_key="alias_suggestion_id",
        apply_callback=_apply_alias_suggestion,
        actor=reviewed_by,
    )
    all_statuses += _apply_suggestion_decisions(
        queryset=list(report.phone_suggestions.all()),
        decisions=phone_decisions,
        id_key="phone_suggestion_id",
        apply_callback=_apply_phone_suggestion,
        actor=reviewed_by,
    )
    all_statuses += _apply_suggestion_decisions(
        queryset=list(report.social_suggestions.all()),
        decisions=social_decisions,
        id_key="social_suggestion_id",
        apply_callback=_apply_social_suggestion,
        actor=reviewed_by,
    )
    all_statuses += _apply_suggestion_decisions(
        queryset=list(report.attachments.all()),
        decisions=attachment_decisions,
        id_key="attachment_id",
        apply_callback=_promote_report_attachment,
        actor=reviewed_by,
    )
    final_statuses = set(all_statuses)

    if not final_statuses or final_statuses == {ReportFieldChangeStatus.APPROVED}:
        final_status = ReportStatus.APPROVED
    elif final_statuses == {ReportFieldChangeStatus.REJECTED}:
        final_status = ReportStatus.REJECTED
    elif ReportFieldChangeStatus.APPROVED in final_statuses:
        final_status = ReportStatus.PARTIALLY_APPROVED
    else:
        final_status = ReportStatus.REJECTED

    report.status = final_status
    report.admin_note = admin_note
    report.reviewed_by = reviewed_by
    report.reviewed_at = timezone.now()
    report.save(
        update_fields=[
            "status",
            "admin_note",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ],
    )

    logger.info(
        "R4J report reviewed report_id=%s final_status=%s approved_count=%s admin=%s",
        report.pk,
        final_status,
        len(approved_changes),
        reviewed_by.pk,
    )

    return report


def _apply_field_changes_to_criminal(
    *,
    criminal: R4JCriminal,
    approved_changes: list[R4JReportFieldChange],
) -> None:
    """
    اعمال type-safe field changeهای approved روی criminal.

    این تابع private است و فقط از داخل review_report صدا زده می‌شود.
    اجرا در همان transaction والد انجام می‌شود.

    از field_applicators برای type normalization استفاده می‌کند.
    فیلدهایی که parse/validation آن‌ها fail می‌شود skip می‌شوند و
    لاگ warning ثبت می‌شود — برای جلوگیری از rollback کل عملیات.
    """
    update_fields: list[str] = ["updated_at"]

    for fc in approved_changes:
        if fc.field_name not in REPORTABLE_CRIMINAL_FIELDS:
            logger.warning(
                "R4J skip non-reportable field field=%s report=%s",
                fc.field_name,
                fc.report_id,
            )
            continue

        try:
            apply_field_to_criminal(
                criminal=criminal,
                field_name=fc.field_name,
                raw_value=fc.suggested_value,
            )
            update_fields.append(fc.field_name)
        except FieldApplicationError as exc:
            logger.warning(
                "R4J field application failed field=%s report=%s reason=%s",
                fc.field_name,
                fc.report_id,
                exc.reason,
            )
            fc.status = ReportFieldChangeStatus.REJECTED
            fc.admin_note = f"اعمال خودکار ناموفق: {exc.reason}"
            fc.save(update_fields=["status", "admin_note", "updated_at"])

    if len(update_fields) > 1:
        criminal.save(update_fields=list(set(update_fields)))
        logger.info(
            "R4J criminal updated via report criminal=%s fields=%s",
            criminal.pk,
            sorted(set(update_fields) - {"updated_at"}),
        )


# ============================================================
# Reports — cancel approve / reject (توسط admin)
# ============================================================


@transaction.atomic
def approve_report_cancel(
    *,
    report: R4JReport,
    admin: User,
    admin_note: str = "",
) -> R4JReport:
    """
    تأیید درخواست لغو گزارش توسط ادمین.

    فقط گزارش‌های در وضعیت CANCEL_REQUESTED قابل پذیرش هستند.

    Args:
        report: گزارش مورد نظر.
        admin: ادمین تأییدکننده.
        admin_note: یادداشت اختیاری ادمین.

    Raises:
        ReportNotInCancelRequested: اگر وضعیت گزارش cancel_requested نباشد.
    """
    if report.status != ReportStatus.CANCEL_REQUESTED:
        raise ReportNotInCancelRequested(
            "این گزارش در وضعیت درخواست لغو نیست.",
        )

    report.status = ReportStatus.CANCELED
    report.canceled_at = timezone.now()
    report.admin_note = admin_note
    report.reviewed_by = admin
    report.reviewed_at = timezone.now()
    report.save(
        update_fields=[
            "status",
            "canceled_at",
            "admin_note",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ],
    )

    logger.info(
        "R4J report cancel approved report_id=%s admin=%s",
        report.pk,
        admin.pk,
    )

    return report


@transaction.atomic
def reject_report_cancel(
    *,
    report: R4JReport,
    admin: User,
    admin_note: str = "",
) -> R4JReport:
    """
    رد درخواست لغو گزارش توسط ادمین — گزارش به PENDING برمی‌گردد.

    Args:
        report: گزارش مورد نظر.
        admin: ادمین رددهنده.
        admin_note: یادداشت اختیاری ادمین.

    Raises:
        ReportNotInCancelRequested: اگر وضعیت گزارش cancel_requested نباشد.
    """
    if report.status != ReportStatus.CANCEL_REQUESTED:
        raise ReportNotInCancelRequested(
            "این گزارش در وضعیت درخواست لغو نیست.",
        )

    report.status = ReportStatus.PENDING
    report.cancel_requested_at = None
    report.admin_note = admin_note
    report.save(
        update_fields=["status", "cancel_requested_at", "admin_note", "updated_at"],
    )

    logger.info(
        "R4J report cancel rejected report_id=%s admin=%s back_to_pending=True",
        report.pk,
        admin.pk,
    )

    return report


# ============================================================
# Bounties — helpers (private)
# ============================================================


def _validate_bounty_amount_or_raise(*, amount_toman: int) -> None:
    """
    اعتبارسنجی مبلغ bounty و تبدیل خطای Django به service exception.

    Args:
        amount_toman: مبلغ به تومان.

    Raises:
        InvalidBountyAmount: اگر مبلغ کمتر از حداقل مجاز یا نامعتبر باشد.
    """
    try:
        validate_bounty_amount(amount_toman)
    except ValidationError as exc:
        raise InvalidBountyAmount(exc.messages[0]) from exc


def _lock_criminal_for_bounty_sync(*, criminal: R4JCriminal) -> R4JCriminal:
    """
    lock کردن ردیف criminal برای جلوگیری از race condition در sync counters.

    این lock باعث می‌شود mutationهای bounty روی یک criminal خاص
    در transactionهای موازی serial شوند و counter drift رخ ندهد.

    Args:
        criminal: instance مجرم.

    Returns:
        نسخه lock شده‌ی criminal.
    """
    return R4JCriminal.all_objects.select_for_update().get(pk=criminal.pk)


def _sync_criminal_bounty_counters(*, criminal: R4JCriminal) -> R4JCriminal:
    """
    بازمحاسبه و sync کردن counterهای denormalized bounty روی criminal.

    فیلدهایی که sync می‌شوند:
    - total_bounty_toman: مجموع مبالغ bountyهای active + cancel_requested
    - bounties_count: تعداد bountyهای active + cancel_requested

    فقط bountyهای با status داخل BOUNTY_ACTIVE_STATUSES در نظر گرفته می‌شوند
    تا bountyهای لغو شده در مبلغ کل محاسبه نشوند.

    Args:
        criminal: مجرم lock شده.

    Returns:
        criminal به‌روزشده.
    """
    aggregates = R4JBounty.objects.filter(
        criminal=criminal,
        status__in=BOUNTY_ACTIVE_STATUSES,
    ).aggregate(
        total_amount=Sum("amount_toman"),
        total_count=Count("id"),
    )

    criminal.total_bounty_toman = aggregates["total_amount"] or 0
    criminal.bounties_count = aggregates["total_count"] or 0
    criminal.save(
        update_fields=["total_bounty_toman", "bounties_count", "updated_at"],
    )

    logger.info(
        "R4J bounty counters synced criminal=%s total=%s count=%s",
        criminal.pk,
        criminal.total_bounty_toman,
        criminal.bounties_count,
    )

    return criminal


# ============================================================
# Bounties — set / update
# ============================================================


@transaction.atomic
def set_or_update_bounty(
    *,
    criminal: R4JCriminal,
    user: User,
    amount_toman: int,
) -> tuple[R4JBounty, bool]:
    """
    ساخت یا ویرایش bounty فعال کاربر برای یک criminal.

    منطق:
    - اگر bounty با وضعیت ACTIVE برای این user+criminal وجود داشته باشد،
      همان bounty update می‌شود.
    - اگر bounty با وضعیت CANCEL_REQUESTED وجود داشته باشد، update مجاز نیست
      چون bounty در انتظار تصمیم ادمین است.
    - اگر bounty فعال/در انتظار لغو وجود نداشته باشد، bounty جدید ساخته می‌شود.
    - bountyهای CANCELED تاریخی باقی می‌مانند و bounty جدید مجاز است.

    Concurrency:
    - criminal row با select_for_update lock می‌شود.
    - lookup و mutation در همان transaction انجام می‌شود.

    Args:
        criminal: مجرم مقصد.
        user: کاربر تعیین‌کننده جایزه.
        amount_toman: مبلغ به تومان.

    Returns:
        tuple[R4JBounty, bool]:
            - bounty: instance ساخته یا ویرایش‌شده.
            - created: True اگر bounty جدید ساخته شده، False اگر update شده.

    Raises:
        InvalidBountyAmount: مبلغ نامعتبر است.
        BountyUpdateNotAllowed: bounty در وضعیت cancel_requested است.
    """
    _validate_bounty_amount_or_raise(amount_toman=amount_toman)

    locked_criminal = _lock_criminal_for_bounty_sync(criminal=criminal)

    existing_bounty = (
        R4JBounty.objects.select_for_update()
        .filter(
            criminal_id=locked_criminal.pk,
            user_id=user.pk,
            status__in=[BountyStatus.ACTIVE, BountyStatus.CANCEL_REQUESTED],
        )
        .order_by("-created_at")
        .first()
    )

    if existing_bounty and existing_bounty.status == BountyStatus.CANCEL_REQUESTED:
        raise BountyUpdateNotAllowed(
            "درخواست لغو این جایزه در حال بررسی است و تا تعیین تکلیف ادمین "
            "امکان ویرایش یا ثبت مجدد آن وجود ندارد.",
        )

    created = False

    if existing_bounty:
        existing_bounty.amount_toman = amount_toman
        existing_bounty.admin_note = ""
        existing_bounty.save(update_fields=["amount_toman", "admin_note", "updated_at"])
        bounty = existing_bounty
        logger.info(
            "R4J bounty updated bounty_id=%s user=%s criminal=%s amount=%s",
            bounty.pk,
            user.pk,
            locked_criminal.pk,
            amount_toman,
        )
    else:
        bounty = R4JBounty.objects.create(
            criminal=locked_criminal,
            user=user,
            amount_toman=amount_toman,
            status=BountyStatus.ACTIVE,
        )
        created = True
        logger.info(
            "R4J bounty created bounty_id=%s user=%s criminal=%s amount=%s",
            bounty.pk,
            user.pk,
            locked_criminal.pk,
            amount_toman,
        )

    _sync_criminal_bounty_counters(criminal=locked_criminal)
    return bounty, created


# ============================================================
# Bounties — cancel request (user)
# ============================================================


@transaction.atomic
def request_bounty_cancel(*, bounty: R4JBounty, user: User) -> R4JBounty:
    """
    ثبت درخواست لغو bounty توسط owner.

    فقط bountyهای ACTIVE قابل درخواست لغو هستند.
    bountyهای CANCEL_REQUESTED یا CANCELED از این مسیر عبور نمی‌کنند.

    Concurrency:
    - criminal row lock می‌شود برای sync ایمن counters.
    - bounty row هم lock می‌شود برای جلوگیری از concurrent cancel.

    Args:
        bounty: bounty مورد نظر.
        user: کاربر درخواست‌دهنده (باید owner باشد — در view enforce می‌شود).

    Raises:
        BountyNotCancelable: اگر bounty در وضعیت ACTIVE نباشد.
    """
    if bounty.status != BountyStatus.ACTIVE:
        raise BountyNotCancelable(
            "فقط جایزه‌های فعال قابل درخواست لغو هستند.",
        )

    locked_criminal = _lock_criminal_for_bounty_sync(criminal=bounty.criminal)
    locked_bounty = R4JBounty.objects.select_for_update().get(pk=bounty.pk)

    locked_bounty.status = BountyStatus.CANCEL_REQUESTED
    locked_bounty.cancel_requested_at = timezone.now()
    locked_bounty.save(
        update_fields=["status", "cancel_requested_at", "updated_at"],
    )

    _sync_criminal_bounty_counters(criminal=locked_criminal)

    logger.info(
        "R4J bounty cancel requested bounty_id=%s user=%s",
        locked_bounty.pk,
        user.pk,
    )

    return locked_bounty


# ============================================================
# Bounties — admin cancel approve / reject
# ============================================================


@transaction.atomic
def approve_bounty_cancel(
    *,
    bounty: R4JBounty,
    admin: User,
    admin_note: str = "",
) -> R4JBounty:
    """
    تأیید درخواست لغو bounty توسط ادمین.

    فقط bountyهای در وضعیت CANCEL_REQUESTED قابل approve هستند.
    بعد از approve، bounty از محاسبه total خارج می‌شود و counters sync می‌شوند.

    Args:
        bounty: bounty مورد نظر.
        admin: ادمین تصمیم‌گیر.
        admin_note: یادداشت اختیاری ادمین.

    Raises:
        BountyNotInCancelRequested: اگر bounty در وضعیت cancel_requested نباشد.
    """
    if bounty.status != BountyStatus.CANCEL_REQUESTED:
        raise BountyNotInCancelRequested(
            "این جایزه در وضعیت درخواست لغو نیست.",
        )

    locked_criminal = _lock_criminal_for_bounty_sync(criminal=bounty.criminal)
    locked_bounty = R4JBounty.objects.select_for_update().get(pk=bounty.pk)

    locked_bounty.status = BountyStatus.CANCELED
    locked_bounty.canceled_at = timezone.now()
    locked_bounty.admin_note = admin_note
    locked_bounty.save(
        update_fields=["status", "canceled_at", "admin_note", "updated_at"],
    )

    _sync_criminal_bounty_counters(criminal=locked_criminal)

    logger.info(
        "R4J bounty cancel approved bounty_id=%s admin=%s",
        locked_bounty.pk,
        admin.pk,
    )

    return locked_bounty


@transaction.atomic
def reject_bounty_cancel(
    *,
    bounty: R4JBounty,
    admin: User,
    admin_note: str = "",
) -> R4JBounty:
    """
    رد درخواست لغو bounty توسط ادمین.

    bounty به وضعیت ACTIVE برمی‌گردد و در محاسبه total باقی می‌ماند.
    counters re-sync می‌شوند برای اطمینان از consistency.

    Args:
        bounty: bounty مورد نظر.
        admin: ادمین تصمیم‌گیر.
        admin_note: یادداشت اختیاری ادمین.

    Raises:
        BountyNotInCancelRequested: اگر bounty در وضعیت cancel_requested نباشد.
    """
    if bounty.status != BountyStatus.CANCEL_REQUESTED:
        raise BountyNotInCancelRequested(
            "این جایزه در وضعیت درخواست لغو نیست.",
        )

    locked_criminal = _lock_criminal_for_bounty_sync(criminal=bounty.criminal)
    locked_bounty = R4JBounty.objects.select_for_update().get(pk=bounty.pk)

    locked_bounty.status = BountyStatus.ACTIVE
    locked_bounty.cancel_requested_at = None
    locked_bounty.admin_note = admin_note
    locked_bounty.save(
        update_fields=["status", "cancel_requested_at", "admin_note", "updated_at"],
    )

    _sync_criminal_bounty_counters(criminal=locked_criminal)

    logger.info(
        "R4J bounty cancel rejected bounty_id=%s admin=%s back_to_active=True",
        locked_bounty.pk,
        admin.pk,
    )

    return locked_bounty


@transaction.atomic
def record_evidence_custody_review(
    *,
    event: R4JEvidenceCustodyEvent,
    actor: User,
    event_type: str,
    note: str = "",
) -> R4JEvidenceCustodyEvent:
    """Append a human custody review/transfer/reject event for same evidence target."""
    if event_type not in {
        EvidenceCustodyEventType.REVIEWED,
        EvidenceCustodyEventType.TRANSFERRED,
        EvidenceCustodyEventType.REJECTED,
        EvidenceCustodyEventType.DELETED,
    }:
        raise R4JServiceError("نوع رویداد custody نامعتبر است.")
    return _create_custody_event(
        criminal_attachment=event.criminal_attachment,
        report_attachment=event.report_attachment,
        event_type=event_type,
        actor=actor,
        note=note,
        metadata={"source_event_id": event.pk},
    )
