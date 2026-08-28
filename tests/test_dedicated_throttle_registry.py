"""
Dedicated throttle registry — یافتهٔ ممیزی ۵.۱.

ممیزی مستقل نشان داد ۹ endpoint عمومی فقط به پیش‌فرض `anon: 60/min` تکیه
می‌کنند و throttle اختصاصی ندارند؛ در این‌بین `MadadkarPublicReceiptVerifyView`
و `LMSCertificateVerifyView` الگوی «اوراکل شمارش» هستند و با چرخش IP عملاً
بدون سقف مؤثر می‌ماندند، و `CustomTokenRefreshView` در هر فراخوانی یک ردیف
blacklist می‌سازد (هزینهٔ نگارش DB به‌ازای هر درخواست).

این ماژول سه لایه را قفل می‌کند:
1. سیم‌کشی: هر view موردنظر دقیقاً throttle اختصاصی خودش را دارد.
2. ثبت scope: هر scope در `DEFAULT_THROTTLE_RATES` با نرخ تعیین‌شده هست.
3. رفتار: bucket اصلی هر throttle (per-IP و مستقل از احراز هویت) واقعاً
   درخواست را بعد از سهمیه رد می‌کند — نه فقط نام کلاس روی view باشد.

نکته: conftest عمداً `check_throttles` را در اجرای معمول no-op می‌کند،
بنابراین رفتار throttle مستقیم روی نمونهٔ کلاس آزموده می‌شود (مثل تست
health detailed) و سیم‌کشی/ثبت از مسیر settings بررسی می‌شود.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser

from tests.factories import AdminUserFactory, UserFactory

pytestmark = pytest.mark.django_db


class _View:
    pass


class _Request:
    """Double درخواست برای فراخوانی مستقیم throttle.

    ``headers`` لازم است چون از DRF 3.18 ``BaseThrottle.get_ident`` به‌جای
    ``request.META`` از ``request.headers`` می‌خواند؛ بدون آن
    AttributeError می‌گیریم.
    """

    def __init__(self, user, remote_addr: str) -> None:
        self.user = user
        self.META = {"REMOTE_ADDR": remote_addr}
        self.headers = {}


def _checked(throttle, *, ip: str = "203.0.113.50", user=None) -> bool:
    """اجرای allow_request با درخواست ساختگی؛ rate فقط توسط caller تنظیم شده است."""
    return throttle.allow_request(_Request(user=user or AnonymousUser(), remote_addr=ip), _View())


# ============================================================
# ۱ — سیم‌کشی views
# ============================================================


class TestViewWiring:
    """هر endpoint عمومی ممیزی‌شده باید throttle اختصاصی خودش را داشته باشد."""

    def test_madadkar_public_receipt_verify_wired(self) -> None:
        from apps.madadkar.throttles import MadadkarReceiptVerifyThrottle
        from apps.madadkar.views import MadadkarPublicReceiptVerifyView

        assert MadadkarReceiptVerifyThrottle in MadadkarPublicReceiptVerifyView.throttle_classes

    def test_lms_certificate_verify_wired(self) -> None:
        from apps.lms.throttles import LMSCertificateVerifyThrottle
        from apps.lms.views import LMSCertificateVerifyView

        assert LMSCertificateVerifyThrottle in LMSCertificateVerifyView.throttle_classes

    def test_token_refresh_wired(self) -> None:
        from apps.authentication.throttles import TokenRefreshThrottle
        from apps.authentication.views import CustomTokenRefreshView

        assert TokenRefreshThrottle in CustomTokenRefreshView.throttle_classes

    def test_report_subject_list_wired(self) -> None:
        from apps.public_reports.throttles import ReportSubjectListThrottle
        from apps.public_reports.views import ReportSubjectListAPIView

        assert ReportSubjectListThrottle in ReportSubjectListAPIView.throttle_classes

    @pytest.mark.parametrize(
        "view_path",
        [
            "apps.lms.views.LMSCategoryPublicListView",
            "apps.lms.views.LMSCategoryPublicDetailView",
            "apps.lms.views.LMSCoursePublicListView",
            "apps.lms.views.LMSCoursePublicDetailView",
            "apps.lms.views.LMSCourseLessonsPublicView",
            "apps.lms.views.LMSLessonPublicDetailView",
        ],
    )
    def test_lms_browse_views_wired(self, view_path: str) -> None:
        import importlib

        from apps.lms.throttles import LMSBrowseAnonThrottle, LMSBrowseUserThrottle

        module_name, class_name = view_path.rsplit(".", 1)
        view_cls = getattr(importlib.import_module(module_name), class_name)

        assert LMSBrowseAnonThrottle in view_cls.throttle_classes
        assert LMSBrowseUserThrottle in view_cls.throttle_classes


# ============================================================
# ۲ — ثبت scopeها در settings
# ============================================================


class TestScopeRegistration:
    """scope هر throttle باید در DEFAULT_THROTTLE_RATES ثبت شده باشد."""

    @pytest.mark.parametrize(
        ("scope", "rate"),
        [
            ("madadkar_receipt_verify", "10/min"),
            ("lms_certificate_verify", "10/min"),
            ("token_refresh", "30/min"),
            ("public_report_subjects", "30/min"),
            ("lms_browse_anon", "60/min"),
            ("lms_browse_user", "120/min"),
        ],
    )
    def test_scope_registered_with_expected_rate(self, scope: str, rate: str) -> None:
        from config.settings import base as base_settings

        rates = base_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        assert scope in rates, f"scope {scope} در DEFAULT_THROTTLE_RATES ثبت نشده است"
        assert rates[scope] == rate


# ============================================================
# ۳ — رفتار bucket
# ============================================================


class TestPerIPThrottleBehavior:
    """throttleهای per-IP باید بعد از سهمیه رد کنند و بین IPها مستقل باشند."""

    @pytest.mark.parametrize(
        "throttle_cls",
        [
            "apps.madadkar.throttles.MadadkarReceiptVerifyThrottle",
            "apps.lms.throttles.LMSCertificateVerifyThrottle",
            "apps.authentication.throttles.TokenRefreshThrottle",
            "apps.public_reports.throttles.ReportSubjectListThrottle",
        ],
    )
    def test_anon_ip_bucket_is_enforced_and_independent(self, throttle_cls: str) -> None:
        import importlib

        module_name, class_name = throttle_cls.rsplit(".", 1)
        cls = getattr(importlib.import_module(module_name), class_name)
        throttle = cls()
        throttle.rate = "3/min"
        throttle.num_requests, throttle.duration = throttle.parse_rate(throttle.rate)

        ip_a = "203.0.113.60"
        assert _checked(throttle, ip=ip_a) is True
        assert _checked(throttle, ip=ip_a) is True
        assert _checked(throttle, ip=ip_a) is True
        assert _checked(throttle, ip=ip_a) is False, "چهارمین درخواست از همان IP باید رد شود"

        # IP دیگر باید bucket مستقل داشته باشد و مجاز باشد.
        assert _checked(throttle, ip="203.0.113.61") is True

    @pytest.mark.parametrize(
        "throttle_cls",
        [
            "apps.madadkar.throttles.MadadkarReceiptVerifyThrottle",
            "apps.lms.throttles.LMSCertificateVerifyThrottle",
            "apps.authentication.throttles.TokenRefreshThrottle",
            "apps.public_reports.throttles.ReportSubjectListThrottle",
        ],
    )
    def test_authenticated_requests_still_keyed_by_ip(self, throttle_cls: str) -> None:
        """این throttleها عمداً «همیشه» روی IP هستند؛ احراز هویت نباید bypass دهد."""
        import importlib

        module_name, class_name = throttle_cls.rsplit(".", 1)
        cls = getattr(importlib.import_module(module_name), class_name)
        throttle = cls()
        throttle.rate = "3/min"
        throttle.num_requests, throttle.duration = throttle.parse_rate(throttle.rate)

        staff = AdminUserFactory()
        ip = "203.0.113.70"
        assert _checked(throttle, ip=ip, user=staff) is True
        assert _checked(throttle, ip=ip, user=staff) is True
        assert _checked(throttle, ip=ip, user=staff) is True
        assert _checked(throttle, ip=ip, user=staff) is False, (
            "حتی کاربرِ احراز هویت‌شده هم از bucket همان IP رد نمی‌شود (anti-enumeration)"
        )


class TestLMSBrowseThrottlePair:
    """جفت anon/user برای browse عمومی LMS — مثل الگوی madadkar/r4j."""

    def test_anon_throttle_keys_by_ip_and_user_throttle_keys_by_user(self) -> None:
        from apps.lms.throttles import LMSBrowseAnonThrottle, LMSBrowseUserThrottle

        anon = LMSBrowseAnonThrottle()
        anon.rate = "3/min"
        anon.num_requests, anon.duration = anon.parse_rate(anon.rate)

        assert _checked(anon, ip="203.0.113.80") is True
        assert _checked(anon, ip="203.0.113.80") is True
        assert _checked(anon, ip="203.0.113.80") is True
        assert _checked(anon, ip="203.0.113.80") is False

        # کاربر لاگین‌شده از AnonRateThrottle عبور می‌کند (طبق طراحی DRF)
        # و باید توسط سهمیهٔ user پوشش داده شود.
        user = UserFactory()
        assert _checked(anon, ip="203.0.113.81", user=user) is True

        user_throttle = LMSBrowseUserThrottle()
        user_throttle.rate = "3/min"
        user_throttle.num_requests, user_throttle.duration = user_throttle.parse_rate(
            user_throttle.rate
        )
        assert _checked(user_throttle, ip="203.0.113.82", user=user) is True
        assert _checked(user_throttle, ip="203.0.113.82", user=user) is True
        assert _checked(user_throttle, ip="203.0.113.82", user=user) is True
        assert _checked(user_throttle, ip="203.0.113.82", user=user) is False
