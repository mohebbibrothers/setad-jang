"""AppConfig for Kindness Wall."""

from django.apps import AppConfig


class KindnessWallConfig(AppConfig):
    """Application configuration for Divar-e Mehrabani."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kindness_wall"
    verbose_name = "دیوار مهربانی"

    def ready(self) -> None:
        """Register public cache invalidation signal handlers."""
        from . import signals  # noqa: F401
