"""
AppConfig for the core infrastructure application.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Application configuration for CoreConfig."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "هسته مرکزی"

    def ready(self) -> None:
        """Apply project-wide admin presentation customizations."""
        from apps.core.admin_i18n import apply_persian_admin_labels

        apply_persian_admin_labels()
