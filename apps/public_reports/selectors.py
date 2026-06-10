from django.db.models import Count, QuerySet

from .models import Report, ReportSubject

# ---------- Subjects ----------


def get_active_subjects() -> QuerySet[ReportSubject]:
    """موضوعات فعال برای نمایش به کاربر عمومی."""
    return ReportSubject.objects.all()


def get_all_subjects_for_admin() -> QuerySet[ReportSubject]:
    """همه موضوعات (شامل غیرفعال‌ها) برای ادمین، همراه با تعداد گزارش‌ها."""
    return ReportSubject.all_objects.annotate(reports_count=Count("reports")).order_by(
        "order", "title"
    )


def get_subject_by_id_for_admin(subject_id: int) -> ReportSubject | None:
    return (
        ReportSubject.all_objects.annotate(reports_count=Count("reports"))
        .filter(id=subject_id)
        .first()
    )


# ---------- Reports ----------


def get_all_reports() -> QuerySet[Report]:
    return Report.objects.select_related("subject").prefetch_related("attachments")


def get_report_by_id(report_id: int) -> Report | None:
    return (
        Report.objects.select_related("subject")
        .prefetch_related("attachments")
        .filter(id=report_id)
        .first()
    )
