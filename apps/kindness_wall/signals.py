"""Handlerهای ابطال کش عمومی دیوار مهربانی.

هر تغییر روی محتوای تخته (دسته/آگهی/تصویر) یا شمارندهٔ اعلام‌ها (Offer)
باید کش دامنهٔ «kindness» را بشکند؛ bulk-update تسک انقضا چون سیگنال
نمی‌فرستد، ابطالش دستی در خود تسک انجام می‌شود.
"""

from __future__ import annotations

import logging

from apps.core.cache_signals import register_public_cache_invalidation
from apps.kindness_wall.models import (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessOffer,
)

logger = logging.getLogger("apps.kindness_wall.signals")

PUBLIC_INVALIDATION_MODELS = (
    KindnessCategory,
    KindnessListing,
    KindnessListingImage,
    KindnessOffer,
)

register_public_cache_invalidation(
    domain="kindness",
    models=PUBLIC_INVALIDATION_MODELS,
    logger=logger,
)
