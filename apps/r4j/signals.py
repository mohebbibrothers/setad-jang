"""R4J cache invalidation signal handlers."""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache_invalidation import invalidate_public_domain
from apps.r4j.models import (
    R4JBounty,
    R4JCriminal,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JCriminalPhoto,
    R4JCriminalSocial,
)

logger = logging.getLogger("apps.r4j.signals")

R4J_PUBLIC_INVALIDATION_MODELS = (
    R4JCriminal,
    R4JCriminalPhoto,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JCriminalSocial,
    R4JBounty,
)


def _invalidate_r4j_public_cache(sender_name: str, instance_pk: int | None) -> None:
    """Invalidate public R4J and homepage caches for one model event."""
    try:
        invalidate_public_domain("r4j")
        logger.info("R4J public cache invalidation requested sender=%s pk=%s", sender_name, instance_pk)
    except Exception:
        logger.exception("R4J public cache invalidation failed sender=%s pk=%s", sender_name, instance_pk)


@receiver(post_save)
def invalidate_r4j_public_cache_on_save(sender, instance, **kwargs) -> None:
    """Invalidate public R4J caches after relevant model saves."""
    if sender in R4J_PUBLIC_INVALIDATION_MODELS:
        _invalidate_r4j_public_cache(sender.__name__, getattr(instance, "pk", None))


@receiver(post_delete)
def invalidate_r4j_public_cache_on_delete(sender, instance, **kwargs) -> None:
    """Invalidate public R4J caches after relevant model deletes."""
    if sender in R4J_PUBLIC_INVALIDATION_MODELS:
        _invalidate_r4j_public_cache(sender.__name__, getattr(instance, "pk", None))
