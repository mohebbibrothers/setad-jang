"""Public cache invalidation signal handlers for public_reports."""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache_invalidation import invalidate_public_domain
from apps.public_reports.models import (
    Report,
    ReportAttachment,
    ReportSubject,
)

logger = logging.getLogger("apps.public_reports.signals")

PUBLIC_INVALIDATION_MODELS = (
    ReportSubject,
    Report,
    ReportAttachment,
)


def _invalidate_public_cache(sender_name: str, instance_pk: int | None) -> None:
    """Invalidate public public_reports and homepage caches for one model event."""
    try:
        invalidate_public_domain("public_reports")
        logger.info("Public cache invalidation requested domain=public_reports sender=%s pk=%s", sender_name, instance_pk)
    except Exception:
        logger.exception("Public cache invalidation failed domain=public_reports sender=%s pk=%s", sender_name, instance_pk)


@receiver(post_save)
def invalidate_public_cache_on_save(sender, instance, **kwargs) -> None:
    """Invalidate public caches after relevant model saves."""
    if sender in PUBLIC_INVALIDATION_MODELS:
        _invalidate_public_cache(sender.__name__, getattr(instance, "pk", None))


@receiver(post_delete)
def invalidate_public_cache_on_delete(sender, instance, **kwargs) -> None:
    """Invalidate public caches after relevant model deletes."""
    if sender in PUBLIC_INVALIDATION_MODELS:
        _invalidate_public_cache(sender.__name__, getattr(instance, "pk", None))
