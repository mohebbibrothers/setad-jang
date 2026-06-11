"""Throttle classes for Support Desk APIs."""

from rest_framework.throttling import UserRateThrottle


class SupportTicketCreateThrottle(UserRateThrottle):
    """Throttle ticket creation attempts."""

    scope = "support_ticket_create"


class SupportTicketMessageThrottle(UserRateThrottle):
    """Throttle ticket message replies."""

    scope = "support_ticket_message"


class SupportAttachmentUploadThrottle(UserRateThrottle):
    """Throttle support attachment uploads."""

    scope = "support_attachment_upload"


class SupportSuggestThrottle(UserRateThrottle):
    """Throttle smart triage suggestion requests."""

    scope = "support_suggest"
