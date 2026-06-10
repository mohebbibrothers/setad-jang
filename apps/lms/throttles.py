"""
Throttle classes for LMS endpoints.

Concrete scopes are registered in settings as API phases are implemented.
"""

from rest_framework.throttling import UserRateThrottle


class LMSEnrollThrottle(UserRateThrottle):
    """Rate limit course enrollment attempts."""

    scope = "lms_enroll"


class LMSProgressThrottle(UserRateThrottle):
    """Rate limit lesson progress updates."""

    scope = "lms_progress"


class LMSQuizStartThrottle(UserRateThrottle):
    """Rate limit quiz attempt starts."""

    scope = "lms_quiz_start"


class LMSDiscussionThrottle(UserRateThrottle):
    """Rate limit lesson Q&A posts."""

    scope = "lms_discussion"
