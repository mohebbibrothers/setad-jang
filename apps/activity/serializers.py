"""Serializers for activity timeline."""

from rest_framework import serializers

from apps.activity.models import UserActivity


class UserActivitySerializer(serializers.ModelSerializer):
    """User activity timeline serializer."""

    actor_display = serializers.SerializerMethodField()

    class Meta:
        model = UserActivity
        fields = (
            "id",
            "event_type",
            "app_label",
            "verb",
            "title",
            "summary",
            "aggregate_type",
            "aggregate_id",
            "actor_id",
            "actor_display",
            "metadata",
            "created_at",
        )
        read_only_fields = fields

    def get_actor_display(self, obj: UserActivity) -> str:
        """Return safe actor display name."""
        if obj.actor is None:
            return ""
        return getattr(obj.actor, "full_name", "") or str(obj.actor)
