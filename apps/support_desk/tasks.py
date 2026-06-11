"""Celery tasks for Support Desk maintenance and operations."""

from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.support_desk.choices import TicketStatus
from apps.support_desk.models import SupportTicket
from apps.support_desk.services import mark_sla_breaches


@shared_task(name="apps.support_desk.tasks.mark_support_sla_breaches_task", ignore_result=False)
def mark_support_sla_breaches_task() -> int:
    """Mark SLA-breached support tickets and return affected count."""
    return mark_sla_breaches()


@shared_task(name="apps.support_desk.tasks.cleanup_stale_support_drafts_task", ignore_result=False)
def cleanup_stale_support_drafts_task(*, older_than_days: int = 30) -> int:
    """Archive stale draft tickets that were never submitted."""
    cutoff = timezone.now() - timezone.timedelta(days=older_than_days)
    updated = SupportTicket.objects.filter(status=TicketStatus.DRAFT, created_at__lt=cutoff).update(
        status=TicketStatus.ARCHIVED,
        updated_at=timezone.now(),
    )
    return int(updated)


@shared_task(name="apps.support_desk.tasks.daily_support_digest_task", ignore_result=False)
def daily_support_digest_task() -> dict[str, int]:
    """Return daily support queue digest counters for monitoring hooks."""
    open_tickets = SupportTicket.objects.open_queue()
    return {
        "open_tickets": open_tickets.count(),
        "unassigned_tickets": open_tickets.filter(assigned_to__isnull=True).count(),
        "sla_breached_tickets": open_tickets.filter(sla_breached_at__isnull=False).count(),
    }
