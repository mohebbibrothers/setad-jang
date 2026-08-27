"""R4J cache invalidation signal handlers."""

from __future__ import annotations

import logging

from apps.core.cache_signals import register_public_cache_invalidation
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
    R4JBounty,
    R4JCriminal,
    R4JCriminalAttachment,
    R4JCriminalFieldVisibility,
    R4JCriminalPhoto,
    R4JCriminalSocial,
)

register_public_cache_invalidation(
    domain="r4j",
    models=R4J_PUBLIC_INVALIDATION_MODELS,
    logger=logger,
)
