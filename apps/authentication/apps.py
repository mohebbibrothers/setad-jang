"""
AppConfig bootstrap for authentication signals and services.
"""

from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    """Application configuration for AuthenticationConfig."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authentication"
    verbose_name = "احراز هویت"

    def ready(self):
        from . import signals  # noqa: F401
