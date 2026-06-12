"""Application config for user activity timeline."""

from django.apps import AppConfig


class ActivityConfig(AppConfig):
    """Django app config for cross-app user activity timeline."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.activity"
    verbose_name = "خط زمانی فعالیت کاربران"
