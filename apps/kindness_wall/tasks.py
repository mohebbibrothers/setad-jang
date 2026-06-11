"""Celery tasks for Kindness Wall maintenance."""

from celery import shared_task


@shared_task(name="apps.kindness_wall.tasks.expire_old_listings_task", ignore_result=True)
def expire_old_listings_task() -> None:
    """Future task hook for expiring old listings."""
    return None
