"""
AppConfig for the audit logs application.
"""

from django.apps import AppConfig


class AuditLogsConfig(AppConfig):
    """Application configuration for AuditLogsConfig."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit_logs"
    verbose_name = "لاگ فعالیت‌ها"
