"""Public cache invalidation signal handlers for madadkar."""

from __future__ import annotations

import logging

from apps.core.cache_signals import register_public_cache_invalidation
from apps.madadkar.models import (
    Campaign,
    CampaignDisbursement,
    CampaignImage,
)

logger = logging.getLogger("apps.madadkar.signals")

# فقط مدل‌هایی که تغییرشان روی داده‌ی عمومی اثر دارد و توسط مدل دیگری
# پوشش داده نمی‌شود.
#
# چرا Payment / Participation / PaymentRefund / CampaignFinancialAdjustment /
# DonationReceipt از این لیست حذف شدند:
#     هر مسیری که این مدل‌ها را تغییر می‌دهد در انتها
#     `_sync_campaign_counters()` را صدا می‌زند که خودش `campaign.save()`
#     می‌کند و در نتیجه گیرنده‌ی Campaign را فعال می‌کند. بنابراین حضورشان
#     در این لیست صرفاً تکراری بود و باعث می‌شد یک donation منجر به ۲۱ بار
#     invalidate کردن کل کش عمومی مددکار شود — یعنی کش عمومی یک کمپین فعال
#     هرگز warm نمی‌شد و ISR فرانت‌اند دائماً کوبیده می‌شد.
#     DonationReceipt اساساً داده‌ی خصوصیِ یک کاربر است و هرگز عمومی نبود.
PUBLIC_INVALIDATION_MODELS = (
    Campaign,
    CampaignImage,
    CampaignDisbursement,
)

register_public_cache_invalidation(
    domain="madadkar",
    models=PUBLIC_INVALIDATION_MODELS,
    logger=logger,
)
