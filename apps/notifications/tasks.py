"""Celery tasks for notification dispatch."""

from celery import shared_task

from apps.notifications.models import NotificationEvent
from apps.notifications.services import dispatch_event


@shared_task(name="apps.notifications.tasks.dispatch_notification_event_task", ignore_result=False)
def dispatch_notification_event_task(event_id: int) -> str:
    """Dispatch one notification event asynchronously."""
    event = NotificationEvent.objects.get(pk=event_id)
    dispatch_event(event=event)
    return event.status
