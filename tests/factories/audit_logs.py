"""
Factories اپ audit_logs.

این factory برای ساخت AuditLog نمونه در تست‌ها استفاده می‌شود.

اصول طراحی:
- مقادیر پیش‌فرض باید معنادار باشند تا تست‌ها بدون override هم خوانا باشند.
- user به‌صورت SubFactory ساخته می‌شود تا وابستگی تست‌ها شفاف باشد.
- هیچ business logic داخل factory نیست؛ فقط ساخت داده.
"""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.models import AuditLog
from tests.factories.auth import UserFactory


class AuditLogFactory(DjangoModelFactory):
    """Factory برای ساخت یک AuditLog نمونه در تست‌ها."""

    class Meta:
        model = AuditLog

    user = factory.SubFactory(UserFactory)
    action = audit_actions.LOGIN_SUCCESS
    resource_type = "user"
    resource_id = factory.LazyAttribute(
        lambda obj: str(obj.user.pk) if obj.user else None,
    )
    ip_address = "127.0.0.1"
    request_id = factory.Sequence(lambda n: f"req-{n:06d}")
    user_agent = "pytest-agent/1.0"
    path = "/api/v1/test/"
    method = "GET"
    changes = None
    extra_data = None
