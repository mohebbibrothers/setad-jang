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
