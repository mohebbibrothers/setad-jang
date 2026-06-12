"""Selectors for user activity timeline."""

from django.db.models import QuerySet

from apps.activity.models import UserActivity


def get_user_activities(*, user_id: int) -> QuerySet[UserActivity]:
    """Return private timeline events for a user."""
    return UserActivity.objects.filter(user_id=user_id).select_related("actor").order_by("-created_at")


def get_user_activity_by_id(*, user_id: int, activity_id: int) -> UserActivity | None:
    """Return one user-owned activity event."""
    return get_user_activities(user_id=user_id).filter(pk=activity_id).first()


def get_admin_activities() -> QuerySet[UserActivity]:
    """Return all activities for admin inspection."""
    return UserActivity.objects.select_related("user", "actor").order_by("-created_at")
