"""Frontend on-demand revalidation integration.

Backend mutations call this module after transaction commit to invalidate the
Next.js data/page cache. The actual HTTP call is delegated to Celery when
available, and is best-effort: a frontend revalidation outage must never make a
business mutation fail.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from django.conf import settings

logger = logging.getLogger("apps.core.frontend_revalidation")


def normalize_tags(tags: Iterable[str] | None) -> list[str]:
    """Return unique, non-empty frontend revalidation tags."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags or []:
        clean = str(tag).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result[:50]


def normalize_paths(paths: Iterable[str] | None) -> list[str]:
    """Return unique, safe absolute paths for frontend revalidation."""
    seen: set[str] = set()
    result: list[str] = []
    for path in paths or []:
        clean = str(path).strip()
        if clean.startswith("/") and not clean.startswith("//") and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result[:50]


def revalidate_frontend(
    *, tags: Iterable[str] | None = None, paths: Iterable[str] | None = None
) -> None:
    """Best-effort dispatch of a frontend revalidation request."""
    clean_tags = normalize_tags(tags)
    clean_paths = normalize_paths(paths)

    if not clean_tags and not clean_paths:
        return

    if not getattr(settings, "FRONTEND_REVALIDATION_ENABLED", False):
        logger.debug("Frontend revalidation disabled tags=%s paths=%s", clean_tags, clean_paths)
        return

    if not getattr(settings, "FRONTEND_REVALIDATION_URL", ""):
        logger.warning("Frontend revalidation enabled but FRONTEND_REVALIDATION_URL is empty")
        return

    try:
        from apps.core.tasks import revalidate_frontend_task

        revalidate_frontend_task.delay(tags=clean_tags, paths=clean_paths)
        logger.info("Frontend revalidation queued tags=%s paths=%s", clean_tags, clean_paths)
    except Exception:
        logger.exception(
            "Failed to queue frontend revalidation tags=%s paths=%s", clean_tags, clean_paths
        )
