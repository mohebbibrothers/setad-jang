"""Throttle classes for Kindness Wall."""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class KindnessBrowseAnonThrottle(AnonRateThrottle):
    """Anonymous browse throttle."""

    scope = "kindness_browse_anon"


class KindnessBrowseUserThrottle(UserRateThrottle):
    """Authenticated browse throttle."""

    scope = "kindness_browse_user"


class KindnessListingCreateThrottle(UserRateThrottle):
    """Listing creation throttle."""

    scope = "kindness_listing_create"


class KindnessContactRevealThrottle(UserRateThrottle):
    """Contact reveal throttle."""

    scope = "kindness_contact_reveal"


class KindnessReportThrottle(UserRateThrottle):
    """Listing report throttle."""

    scope = "kindness_report"
