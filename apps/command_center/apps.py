"""Application configuration for the admin command center."""

from django.apps import AppConfig


class CommandCenterConfig(AppConfig):
    """Django app config for unified admin command center."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.command_center"
    verbose_name = "مرکز فرماندهی مدیریت"
