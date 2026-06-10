"""
AppConfig for the core infrastructure application.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Application configuration for CoreConfig."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "هسته مرکزی"
