"""Serializers for notifications."""

from rest_framework import serializers

from apps.notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
    NotificationTemplate,
)


class NotificationDeliverySerializer(serializers.ModelSerializer):
    """User notification delivery serializer."""

    class Meta:
        model = NotificationDelivery
        fields = ("id", "channel", "status", "subject", "body", "sent_at", "read_at", "created_at")
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """User notification preference serializer."""

    class Meta:
        model = NotificationPreference
        fields = ("id", "event_type", "channel", "enabled", "created_at", "updated_at")
        read_only_fields = fields


class NotificationPreferenceInputSerializer(serializers.Serializer):
    """Input serializer for setting notification preferences."""

    event_type = serializers.CharField(max_length=160)
    channel = serializers.CharField(max_length=20)
    enabled = serializers.BooleanField()


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """Admin notification template serializer."""

    class Meta:
        model = NotificationTemplate
        fields = ("id", "code", "title", "channel", "subject_template", "body_template", "description", "is_active", "created_at", "updated_at")
        read_only_fields = fields


class NotificationEventSerializer(serializers.ModelSerializer):
    """Admin notification event serializer."""

    deliveries_count = serializers.IntegerField(source="deliveries.count", read_only=True)

    class Meta:
        model = NotificationEvent
        fields = ("id", "uuid", "event_type", "aggregate_type", "aggregate_id", "priority", "status", "attempt_count", "processed_at", "last_error", "deliveries_count", "created_at")
        read_only_fields = fields
