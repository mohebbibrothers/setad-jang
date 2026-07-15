"""Central public cache invalidation helpers."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction

from apps.core.cache import cache_delete_namespace
from apps.core.cache_policy import get_cache_policy
from apps.core.frontend_revalidation import revalidate_frontend
from apps.core.models import CacheInvalidationEvent

logger = logging.getLogger("apps.core.cache_invalidation")


def enqueue_cache_invalidation_event(*, domain: str, tags: list[str], paths: list[str]) -> None:
    """Persist and dispatch one cache invalidation outbox event."""
    event = CacheInvalidationEvent.objects.create(domain=domain, tags=tags, paths=paths)

    try:
        from apps.core.tasks import process_cache_invalidation_event_task

        process_cache_invalidation_event_task.delay(event_id=event.pk)
        logger.info("Cache invalidation outbox event queued id=%s domain=%s", event.pk, domain)
    except Exception:
        logger.exception("Failed to queue cache invalidation outbox event id=%s domain=%s", event.pk, domain)


def invalidate_public_domain(domain: str, *, extra_tags: list[str] | None = None, extra_paths: list[str] | None = None) -> None:
    """Invalidate backend namespaces and schedule frontend revalidation after commit."""
    policy = get_cache_policy(domain)

    for namespace in policy.backend_namespaces:
        cache_delete_namespace(namespace)

    tags = [*policy.frontend_tags, *(extra_tags or [])]
    paths = [*policy.frontend_paths, *(extra_paths or [])]

    def _dispatch() -> None:
        if getattr(settings, "CACHE_INVALIDATION_OUTBOX_ENABLED", True):
            enqueue_cache_invalidation_event(domain=domain, tags=tags, paths=paths)
        else:
            revalidate_frontend(tags=tags, paths=paths)
        logger.info("Public domain invalidated domain=%s tags=%s paths=%s", domain, tags, paths)

    transaction.on_commit(_dispatch)
