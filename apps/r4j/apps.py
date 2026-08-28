"""
AppConfig for the Reward for Justice application.
"""

from django.apps import AppConfig


class R4JConfig(AppConfig):
    """Application configuration for R4JConfig."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.r4j"
    verbose_name = "جایزه‌ای برای عدالت"

    def ready(self) -> None:
        # Register cache invalidation signal handlers.
        from . import signals  # noqa: F401
