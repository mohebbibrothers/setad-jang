"""
AppConfig for the Tabyin ingestion application.
"""

from django.apps import AppConfig


class TabyinConfig(AppConfig):
    """Application configuration for TabyinConfig."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tabyin"
    verbose_name = "جهاد تبیین"
