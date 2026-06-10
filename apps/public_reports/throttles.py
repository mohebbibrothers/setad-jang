"""
Custom throttling scopes for public report submission endpoints.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class ReportCreateAnonThrottle(AnonRateThrottle):
    """ReportCreateAnonThrottle implementation for the public_reports application."""
    scope = "report_create_anon"


class ReportCreateUserThrottle(UserRateThrottle):
    """ReportCreateUserThrottle implementation for the public_reports application."""
    scope = "report_create_user"
