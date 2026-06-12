"""Django admin for notifications."""

from django.contrib import admin

from apps.notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
    NotificationTemplate,
)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    """Admin template management."""

    list_display = ("code", "channel", "title", "is_active")
    list_filter = ("channel", "is_active")
    search_fields = ("code", "title", "body_template")


@admin.register(NotificationEvent)
class NotificationEventAdmin(admin.ModelAdmin):
    """Admin notification event inspection."""

    list_display = ("event_type", "status", "priority", "aggregate_type", "aggregate_id", "created_at")
    list_filter = ("status", "priority", "event_type")
    search_fields = ("event_type", "aggregate_type", "aggregate_id")
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    """Admin delivery inspection."""

    list_display = ("recipient", "channel", "status", "subject", "sent_at", "read_at")
    list_filter = ("channel", "status")
    search_fields = ("recipient__email", "subject", "body")
    raw_id_fields = ("event", "recipient")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """Admin user preference inspection."""

    list_display = ("user", "event_type", "channel", "enabled")
    list_filter = ("channel", "enabled")
    search_fields = ("user__email", "event_type")
    raw_id_fields = ("user",)
