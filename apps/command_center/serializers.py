"""Serializers for admin command center."""

from rest_framework import serializers


class CommandCenterSummarySerializer(serializers.Serializer):
    """Serializer for cross-app command center summary."""

    generated_at = serializers.DateTimeField()
    support = serializers.DictField()
    kindness_wall = serializers.DictField()
    tabyin = serializers.DictField()
    public_reports = serializers.DictField()
    r4j = serializers.DictField()
    madadkar = serializers.DictField()
    lms = serializers.DictField()
    notifications = serializers.DictField()
    activity = serializers.DictField()
    providers = serializers.DictField()
    health = serializers.DictField()
