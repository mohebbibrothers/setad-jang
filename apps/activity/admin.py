"""Django admin for user activity timeline."""

from django.contrib import admin

from apps.activity.models import UserActivity


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    """Admin inspection for user activity events."""

    list_display = ("user", "event_type", "app_label", "verb", "title", "created_at")
    list_filter = ("app_label", "event_type", "verb")
    search_fields = ("user__email", "title", "summary", "aggregate_id")
    raw_id_fields = ("user", "actor")
    readonly_fields = ("created_at", "updated_at")
