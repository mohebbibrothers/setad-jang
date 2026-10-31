"""Throttle classes for Kindness Wall."""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class KindnessBrowseAnonThrottle(AnonRateThrottle):
    """Anonymous browse throttle."""

    scope = "kindness_browse_anon"


class KindnessBrowseUserThrottle(UserRateThrottle):
    """Authenticated browse throttle."""

    scope = "kindness_browse_user"


class KindnessOfferCreateThrottle(UserRateThrottle):
    """Throttle for submitting a readiness offer (per hour)."""

    scope = "kindness_offer_create"


class KindnessViewAnonThrottle(AnonRateThrottle):
    """سقفِ beaconِ بازدید برای مهمان.

    سخاوتمندانه‌تر از «مرور» است چون یک نفر ممکن است چند آگهی را پشتِ‌هم باز
    کند، ولی به‌قدری سخت‌گیرانه که اسکریپتِ شمارش نتواند عدد را باد کند.
    dedupeِ پنجره‌ای لایهٔ دومِ دفاع است.
    """

    scope = "kindness_view_anon"


class KindnessViewUserThrottle(UserRateThrottle):
    """سقفِ beaconِ بازدید برای کاربرِ واردشده."""

    scope = "kindness_view_user"
