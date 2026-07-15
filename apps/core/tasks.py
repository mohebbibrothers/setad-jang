"""Core async tasks."""

from __future__ import annotations

import logging

import requests
from celery import shared_task
from django.conf import settings

from apps.core.frontend_revalidation import normalize_paths, normalize_tags

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
        logger.exception(
            "Frontend revalidation request failed tags=%s paths=%s",
            clean_tags,
            clean_paths,
        )
        raise

    body = response.text[:500]
    if response.status_code >= 500:
        logger.warning(
            "Frontend revalidation server error status=%s tags=%s paths=%s body=%s",
            response.status_code,
            clean_tags,
            clean_paths,
            body,
        )
        response.raise_for_status()

    if response.status_code >= 400:
        logger.warning(
            "Frontend revalidation rejected status=%s tags=%s paths=%s body=%s",
            response.status_code,
            clean_tags,
            clean_paths,
            body,
        )
        return

    logger.info(
        "Frontend revalidation completed status=%s tags=%s paths=%s body=%s",
        response.status_code,
        clean_tags,
        clean_paths,
        body,
    )
