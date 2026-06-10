"""
Selector Layer — audit log queries.

تمام queryهای خواندن audit log از اینجا عبور می‌کنند.
View هرگز مستقیماً با ORM کار نمی‌کند.

اصول طراحی:
- querysetها lazy هستند و filter نهایی در view/filter انجام می‌شود.
- select_related برای user اعمال می‌شود تا N+1 جلوگیری شود.
- تمام audit logs فعال هستند (هرگز soft-delete نمی‌شوند).
"""

from __future__ import annotations

from django.db.models import QuerySet

from .models import AuditLog


def get_all_audit_logs() -> QuerySet[AuditLog]:
    """
    تمام audit logها با select_related روی user.

    خروجی lazy queryset است و pagination/filter در view اعمال می‌شود.
    """
    return AuditLog.objects.select_related("user").all()


def get_audit_log_by_id(audit_log_id: int) -> AuditLog | None:
    """
    دریافت یک audit log با شناسه — شامل user select_related.

    اگر یافت نشود None برمی‌گرداند.
    """
    try:
        return AuditLog.objects.select_related("user").get(pk=audit_log_id)
    except AuditLog.DoesNotExist:
        return None
