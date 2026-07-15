"""Core async tasks."""

from __future__ import annotations

import logging

import requests
from celery import shared_task
from django.conf import settings

from apps.core.frontend_revalidation import normalize_paths, normalize_tags
from apps.core.metrics import (
    CACHE_INVALIDATION_OUTBOX_EVENTS,
    CACHE_INVALIDATION_OUTBOX_OLDEST_PENDING_SECONDS,
    FRONTEND_REVALIDATION_DURATION_SECONDS,
    FRONTEND_REVALIDATIONS_TOTAL,
    monotonic_time,
)

logger = logging.getLogger("apps.core.tasks")


@shared_task(
    name="apps.core.tasks.revalidate_frontend_task",
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
    ignore_result=True,
)
def revalidate_frontend_task(self, *, tags: list[str] | None = None, paths: list[str] | None = None) -> None:
    """Call the Next.js /api/revalidate endpoint with tags/paths."""
    if not getattr(settings, "FRONTEND_REVALIDATION_ENABLED", False):
        logger.debug("Frontend revalidation task skipped: disabled")
        FRONTEND_REVALIDATIONS_TOTAL.labels(outcome="disabled").inc()
        return

    url = getattr(settings, "FRONTEND_REVALIDATION_URL", "")
    secret = getattr(settings, "FRONTEND_REVALIDATION_SECRET", "")
    timeout = getattr(settings, "FRONTEND_REVALIDATION_TIMEOUT", 5)

    if not url or not secret:
        logger.warning("Frontend revalidation task skipped: url/secret not configured")
        FRONTEND_REVALIDATIONS_TOTAL.labels(outcome="not_configured").inc()
        return

    clean_tags = normalize_tags(tags)
    clean_paths = normalize_paths(paths)
    if not clean_tags and not clean_paths:
        logger.debug("Frontend revalidation task skipped: empty payload")
        FRONTEND_REVALIDATIONS_TOTAL.labels(outcome="empty").inc()
        return

    started = monotonic_time()
    outcome = "success"
    try:
        response = requests.post(
            url,
            json={"tags": clean_tags, "paths": clean_paths},
            headers={
                "Authorization": f"Bearer {secret}",
                "Accept": "application/json",
                "User-Agent": "setad-jang-backend-revalidator/1.0",
            },
            timeout=timeout,
        )
    except requests.RequestException:
        outcome = "request_error"
        FRONTEND_REVALIDATIONS_TOTAL.labels(outcome=outcome).inc()
        FRONTEND_REVALIDATION_DURATION_SECONDS.labels(outcome=outcome).observe(monotonic_time() - started)
        logger.exception("Frontend revalidation request failed tags=%s paths=%s", clean_tags, clean_paths)
        raise

    body = response.text[:500]
    if response.status_code >= 500:
        outcome = "server_error"
        FRONTEND_REVALIDATIONS_TOTAL.labels(outcome=outcome).inc()
        FRONTEND_REVALIDATION_DURATION_SECONDS.labels(outcome=outcome).observe(monotonic_time() - started)
        logger.warning(
            "Frontend revalidation server error status=%s tags=%s paths=%s body=%s",
            response.status_code,
            clean_tags,
            clean_paths,
            body,
        )
        response.raise_for_status()

    if response.status_code >= 400:
        outcome = "rejected"
        FRONTEND_REVALIDATIONS_TOTAL.labels(outcome=outcome).inc()
        FRONTEND_REVALIDATION_DURATION_SECONDS.labels(outcome=outcome).observe(monotonic_time() - started)
        logger.warning(
            "Frontend revalidation rejected status=%s tags=%s paths=%s body=%s",
            response.status_code,
            clean_tags,
            clean_paths,
            body,
        )
        return

    FRONTEND_REVALIDATIONS_TOTAL.labels(outcome=outcome).inc()
    FRONTEND_REVALIDATION_DURATION_SECONDS.labels(outcome=outcome).observe(monotonic_time() - started)
    logger.info(
        "Frontend revalidation completed status=%s tags=%s paths=%s body=%s",
        response.status_code,
        clean_tags,
        clean_paths,
        body,
    )


@shared_task(
    name="apps.core.tasks.process_cache_invalidation_event_task",
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
    ignore_result=True,
)
def process_cache_invalidation_event_task(self, *, event_id: int) -> None:
    """Process one durable cache invalidation outbox event."""
    from django.utils import timezone

    from apps.core.models import CacheInvalidationEvent

    event = CacheInvalidationEvent.all_objects.filter(pk=event_id).first()
    if event is None:
        logger.warning("Cache invalidation event not found id=%s", event_id)
        return

    if event.status in {CacheInvalidationEvent.STATUS_SUCCEEDED, CacheInvalidationEvent.STATUS_DEAD}:
        logger.debug("Cache invalidation event already terminal id=%s status=%s", event_id, event.status)
        return

    max_attempts = getattr(settings, "CACHE_INVALIDATION_MAX_ATTEMPTS", 10)
    if event.attempts >= max_attempts:
        event.status = CacheInvalidationEvent.STATUS_DEAD
        event.last_error = f"Maximum attempts exceeded ({max_attempts})"
        event.save(update_fields=["status", "last_error", "updated_at"])
        logger.error("Cache invalidation event moved to dead-letter id=%s", event_id)
        return

    event.status = CacheInvalidationEvent.STATUS_PROCESSING
    event.attempts += 1
    event.save(update_fields=["status", "attempts", "updated_at"])

    try:
        revalidate_frontend_task.run(tags=event.tags, paths=event.paths)
    except Exception as exc:
        event.status = CacheInvalidationEvent.STATUS_DEAD if event.attempts >= max_attempts else CacheInvalidationEvent.STATUS_FAILED
        event.last_error = str(exc)[:4000]
        event.next_attempt_at = timezone.now()
        event.save(update_fields=["status", "last_error", "next_attempt_at", "updated_at"])
        raise

    event.status = CacheInvalidationEvent.STATUS_SUCCEEDED
    event.last_error = ""
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "last_error", "processed_at", "updated_at"])


@shared_task(
    name="apps.core.tasks.process_pending_cache_invalidation_events_task",
    ignore_result=True,
)
def process_pending_cache_invalidation_events_task(*, limit: int | None = None) -> int:
    """Dispatch due pending/failed cache invalidation outbox events in batches."""
    from django.db.models import Q
    from django.utils import timezone

    from apps.core.models import CacheInvalidationEvent

    now = timezone.now()
    batch_limit = limit or getattr(settings, "CACHE_INVALIDATION_BATCH_SIZE", 100)
    batch_limit = max(1, min(batch_limit, 500))
    max_attempts = getattr(settings, "CACHE_INVALIDATION_MAX_ATTEMPTS", 10)

    due_query = (
        Q(status=CacheInvalidationEvent.STATUS_PENDING)
        | Q(status=CacheInvalidationEvent.STATUS_FAILED, next_attempt_at__lte=now)
        | Q(status=CacheInvalidationEvent.STATUS_FAILED, next_attempt_at__isnull=True)
    )
    events = list(
        CacheInvalidationEvent.all_objects.filter(due_query, attempts__lt=max_attempts).order_by("created_at")[:batch_limit]
    )

    for event in events:
        process_cache_invalidation_event_task.delay(event_id=event.pk)

    _update_outbox_metrics()
    logger.info("Queued pending cache invalidation events count=%s", len(events))
    return len(events)


def _update_outbox_metrics() -> None:
    """Update cache invalidation outbox gauges."""
    from django.utils import timezone

    from apps.core.models import CacheInvalidationEvent

    for status in (
        CacheInvalidationEvent.STATUS_PENDING,
        CacheInvalidationEvent.STATUS_PROCESSING,
        CacheInvalidationEvent.STATUS_SUCCEEDED,
        CacheInvalidationEvent.STATUS_FAILED,
        CacheInvalidationEvent.STATUS_DEAD,
    ):
        CACHE_INVALIDATION_OUTBOX_EVENTS.labels(status=status).set(
            CacheInvalidationEvent.all_objects.filter(status=status).count(),
        )

    oldest = (
        CacheInvalidationEvent.all_objects.filter(
            status__in=[CacheInvalidationEvent.STATUS_PENDING, CacheInvalidationEvent.STATUS_FAILED],
        )
        .order_by("created_at")
        .first()
    )
    age = (timezone.now() - oldest.created_at).total_seconds() if oldest else 0
    CACHE_INVALIDATION_OUTBOX_OLDEST_PENDING_SECONDS.set(max(age, 0))
