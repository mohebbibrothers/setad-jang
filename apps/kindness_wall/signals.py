"""Public cache invalidation signal handlers for kindness_wall."""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache_invalidation import invalidate_public_domain
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessListingTag,
    KindnessMatch,
)

logger = logging.getLogger("apps.kindness_wall.signals")

PUBLIC_INVALIDATION_MODELS = (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessListingTag,
    KindnessMatch,
)


def _invalidate_public_cache(sender_name: str, instance_pk: int | None) -> None:
    """Invalidate public kindness_wall and homepage caches for one model event."""
    try:
        invalidate_public_domain("kindness")
        logger.info("Public cache invalidation requested domain=kindness sender=%s pk=%s", sender_name, instance_pk)
    except Exception:
        logger.exception("Public cache invalidation failed domain=kindness sender=%s pk=%s", sender_name, instance_pk)


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
