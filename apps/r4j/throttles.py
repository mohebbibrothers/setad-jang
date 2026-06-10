"""
Throttles اپ R4J.

تنظیمات rate-limit در config/settings/base.py تعریف شده‌اند:
- r4j_browse_anon: 60/min
- r4j_browse_user: 120/min
- r4j_report_create: 5/min
- r4j_bounty_set: 3/min

این فایل کلاس‌های throttle که به آن نرخ‌ها مرتبط می‌شوند را نگه می‌دارد.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class R4JBrowseAnonThrottle(AnonRateThrottle):
    scope = "r4j_browse_anon"


class R4JBrowseUserThrottle(UserRateThrottle):
    scope = "r4j_browse_user"


class R4JReportCreateThrottle(UserRateThrottle):
    scope = "r4j_report_create"


class R4JBountySetThrottle(UserRateThrottle):
    scope = "r4j_bounty_set"
