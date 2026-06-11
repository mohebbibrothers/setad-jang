"""Application configuration for Support Desk."""

from django.apps import AppConfig


class SupportDeskConfig(AppConfig):
    """Django app config for the enterprise support desk."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.support_desk"
    verbose_name = "میز پشتیبانی"
