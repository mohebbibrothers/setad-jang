"""Public cache invalidation signal handlers for lms."""

from __future__ import annotations

import logging

from apps.core.cache_signals import register_public_cache_invalidation
from apps.lms.models import (
    Course,
    Lesson,
    LessonVideoProcessingJob,
    LMSCategory,
    Quiz,
)

logger = logging.getLogger("apps.lms.signals")

PUBLIC_INVALIDATION_MODELS = (
    Course,
    Lesson,
    LessonVideoProcessingJob,
    LMSCategory,
    Quiz,
)

register_public_cache_invalidation(
    domain="lms",
    models=PUBLIC_INVALIDATION_MODELS,
    logger=logger,
)
