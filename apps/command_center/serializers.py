"""Serializers for admin command center."""

from rest_framework import serializers


class CommandCenterSummarySerializer(serializers.Serializer):
    """Serializer for cross-app command center summary."""

    generated_at = serializers.DateTimeField()
    counters_generated_at = serializers.DateTimeField(
        allow_null=True,
        help_text="زمان محاسبهٔ شمارنده‌ها. شمارنده‌ها با stale-while-revalidate کش می‌شوند و می‌توانند تا یک دقیقه کهنه باشند؛ بخش health و providers همیشه زنده است.",
    )
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
