"""Application configuration for notifications."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Django app config for the cross-app notification engine."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    verbose_name = "اعلان‌ها"
