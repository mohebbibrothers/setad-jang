"""Public cache invalidation signal handlers for public_reports."""

from __future__ import annotations

import logging

from apps.core.cache_signals import register_public_cache_invalidation
from apps.public_reports.models import (
    Report,
    ReportAttachment,
    ReportSubject,
)

logger = logging.getLogger("apps.public_reports.signals")

PUBLIC_INVALIDATION_MODELS = (
    Report,
    ReportAttachment,
    ReportSubject,
)

register_public_cache_invalidation(
    domain="public_reports",
    models=PUBLIC_INVALIDATION_MODELS,
    logger=logger,
)
