"""
Throttle classes for LMS endpoints.

Concrete scopes are registered in settings as API phases are implemented.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.core.throttling import ClientIPRateThrottle


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


class LMSBrowseAnonThrottle(AnonRateThrottle):
    """Throttle برای کاربران ناشناس در endpointهای عمومی browse دوره‌ها."""

    scope = "lms_browse_anon"


class LMSBrowseUserThrottle(UserRateThrottle):
    """Throttle برای کاربران لاگین‌شده در endpointهای عمومی browse دوره‌ها."""

    scope = "lms_browse_user"


class LMSCertificateVerifyThrottle(ClientIPRateThrottle):
    """
    Throttle اختصاصی تأیید عمومی گواهی‌نامه (یافتهٔ ممیزی ۵.۱).

    «آیا این کد گواهی معتبر است؟» یک اوراکل شمارش است: مهاجم با چرخش IP
    می‌توانست slugهای گواهی را brute-force کند و اعتبار مدارک دیگران را
    استعلام بگیرد. کلید همیشه روی IP ساخته می‌شود و سقف سخت‌گیرانه است.
    """

    scope = "lms_certificate_verify"
