"""
AppConfig for the public reports application.
"""

from django.apps import AppConfig


class PublicReportsConfig(AppConfig):
    """Application configuration for PublicReportsConfig."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.public_reports"
    verbose_name = "گزارشات مردمی"

    def ready(self) -> None:
        """Register public cache invalidation signal handlers."""
        from . import signals  # noqa: F401

