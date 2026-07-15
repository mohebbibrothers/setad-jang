"""Core async tasks."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from celery import shared_task
from django.conf import settings

from apps.core.frontend_revalidation import normalize_paths, normalize_tags

logger = logging.getLogger("apps.core.tasks")


@shared_task(
    name="apps.core.tasks.revalidate_frontend_task",
    bind=True,
    autoretry_for=(urllib.error.URLError, TimeoutError),
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
        return

    url = getattr(settings, "FRONTEND_REVALIDATION_URL", "")
    secret = getattr(settings, "FRONTEND_REVALIDATION_SECRET", "")
    timeout = getattr(settings, "FRONTEND_REVALIDATION_TIMEOUT", 5)

    if not url or not secret:
        logger.warning("Frontend revalidation task skipped: url/secret not configured")
        return

    clean_tags = normalize_tags(tags)
    clean_paths = normalize_paths(paths)
    if not clean_tags and not clean_paths:
        logger.debug("Frontend revalidation task skipped: empty payload")
        return

    body = json.dumps({"tags": clean_tags, "paths": clean_paths}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {secret}",
            "User-Agent": "setad-jang-backend-revalidator/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            payload = response.read(2048).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        payload = exc.read(2048).decode("utf-8", errors="replace")
        logger.warning(
            "Frontend revalidation HTTP error status=%s tags=%s paths=%s body=%s",
            exc.code,
            clean_tags,
            clean_paths,
            payload[:500],
        )
        if exc.code >= 500:
            raise
        return

    logger.info(
        "Frontend revalidation completed status=%s tags=%s paths=%s body=%s",
        status,
        clean_tags,
        clean_paths,
        payload[:500],
    )
