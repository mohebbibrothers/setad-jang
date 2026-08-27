"""Public cache invalidation signal handlers for kindness_wall."""

from __future__ import annotations

import logging

from apps.core.cache_signals import register_public_cache_invalidation
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

register_public_cache_invalidation(
    domain="kindness",
    models=PUBLIC_INVALIDATION_MODELS,
    logger=logger,
)
