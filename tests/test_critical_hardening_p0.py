"""
Regression tests for the critical (P0) production hardening fixes.

هر تست در این فایل دقیقاً یکی از باگ‌های بحرانی گزارش آنالیز را پوشش
می‌دهد. اگر کسی در آینده یکی از این اصلاح‌ها را برگرداند، همین‌جا قرمز
می‌شود. عنوان هر بخش به شناسه‌ی همان یافته در گزارش اشاره دارد.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from django.db import IntegrityError, transaction
from django.db.models.signals import post_delete, post_save
from django.test import RequestFactory
from rest_framework.parsers import JSONParser
from rest_framework.request import Request

from apps.audit_logs.chain import verify_audit_chain_integrity
from apps.audit_logs.models import GENESIS_HASH, AuditLog
from apps.audit_logs.services import create_audit_log
from apps.authentication import throttles as auth_throttles
from apps.core.throttling import ClientIPRateThrottle, IdentityRateThrottle
from apps.madadkar import throttles as madadkar_throttles

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _AuthenticatedUserStub:
    """کاربر ساختگی احرازشده برای تست کلید throttle بدون نیاز به دیتابیس."""

    is_authenticated = True
    pk = 4242


def _json_request(payload: dict[str, str] | None = None) -> Request:
    """ساخت یک DRF Request واقعی با parser فعال برای تست throttle."""
    import json

    body = json.dumps(payload or {})
    django_request = RequestFactory().post("/x", body, content_type="application/json")
    return Request(django_request, parsers=[JSONParser()])


# ===========================================================================
# A1 — throttleهای احراز هویت نباید برای کاربر لاگین‌کرده bypass شوند
# ===========================================================================


@pytest.mark.parametrize(
    "throttle_class",
    [
        auth_throttles.LoginThrottle,
        auth_throttles.RegisterThrottle,
        auth_throttles.OTPRequestThrottle,
        auth_throttles.OTPVerifyThrottle,
        auth_throttles.OTPGlobalIPThrottle,
        auth_throttles.PasswordResetThrottle,
        madadkar_throttles.MadadkarPaymentVerifyThrottle,
    ],
)
def test_auth_throttles_are_never_bypassed_for_authenticated_users(throttle_class) -> None:
    """
    هیچ throttle حساسی نباید برای کاربر احرازشده کلید None بدهد.

    باگ اصلی: تمام این کلاس‌ها از AnonRateThrottle ارث می‌بردند و
    get_cache_key آن برای کاربر لاگین‌کرده None برمی‌گرداند، پس DRF
    throttle را کاملاً skip می‌کرد. endpointهای identifiers/add/* که
    IsAuthenticated هستند عملاً بدون هیچ محدودیتی اجرا می‌شدند.
    """
    throttle = throttle_class()

    anonymous_request = _json_request({"identifier": "09120000000"})
    authenticated_request = _json_request({"identifier": "09120000000"})
    authenticated_request.user = _AuthenticatedUserStub()

    assert throttle.get_cache_key(anonymous_request, None) is not None
    assert throttle.get_cache_key(authenticated_request, None) is not None


@pytest.mark.parametrize(
    "throttle_class",
    [
        auth_throttles.LoginThrottle,
        auth_throttles.RegisterThrottle,
        auth_throttles.OTPRequestThrottle,
        auth_throttles.OTPVerifyThrottle,
        auth_throttles.PasswordResetThrottle,
    ],
)
def test_identity_throttles_separate_user_and_ip_buckets(throttle_class) -> None:
    """کاربر احرازشده نباید سهمیه‌ی anonymousها را مصرف کند و برعکس."""
    throttle = throttle_class()
    assert isinstance(throttle, IdentityRateThrottle)

    anonymous_request = _json_request()
    authenticated_request = _json_request()
    authenticated_request.user = _AuthenticatedUserStub()

    assert throttle.get_cache_key(anonymous_request, None) != throttle.get_cache_key(
        authenticated_request, None
    )


def test_ip_scoped_throttles_ignore_authentication_state() -> None:
    """لایه‌ی per-IP باید برای کاربر لاگین‌کرده و ناشناس یک bucket بدهد."""
    throttle = auth_throttles.OTPGlobalIPThrottle()
    assert isinstance(throttle, ClientIPRateThrottle)

    anonymous_request = _json_request()
    authenticated_request = _json_request()
    authenticated_request.user = _AuthenticatedUserStub()

    assert throttle.get_cache_key(anonymous_request, None) == throttle.get_cache_key(
        authenticated_request, None
    )


def test_otp_target_throttle_buckets_by_recipient_not_by_caller() -> None:
    """
    سقف per-recipient باید مستقل از هویت مهاجم باشد.

    این تنها لایه‌ای است که جلوی SMS-bombing توزیع‌شده روی یک شماره را
    می‌گیرد: مهاجم می‌تواند IP و اکانت عوض کند، شمارهٔ قربانی نه.
    """
    throttle = auth_throttles.OTPTargetThrottle()

    victim_from_anonymous = _json_request({"identifier": "09120000000"})
    victim_from_authenticated = _json_request({"identifier": "09120000000"})
    victim_from_authenticated.user = _AuthenticatedUserStub()
    other_victim = _json_request({"identifier": "09129999999"})

    key_anonymous = throttle.get_cache_key(victim_from_anonymous, None)
    key_authenticated = throttle.get_cache_key(victim_from_authenticated, None)
    key_other = throttle.get_cache_key(other_victim, None)

    assert key_anonymous == key_authenticated
    assert key_anonymous != key_other


def test_otp_target_throttle_normalises_case_and_hides_plaintext() -> None:
    """هدف باید نرمالایز و هش شود تا شماره/ایمیل وارد cache key نشود."""
    throttle = auth_throttles.OTPTargetThrottle()

    upper = throttle.get_cache_key(_json_request({"email": "A@Example.COM"}), None)
    lower = throttle.get_cache_key(_json_request({"email": "a@example.com"}), None)
    phone_key = throttle.get_cache_key(_json_request({"identifier": "09120000000"}), None)

    assert upper == lower
    assert "a@example.com" not in upper
    assert "09120000000" not in phone_key


def test_otp_target_throttle_falls_through_when_no_target_present() -> None:
    """نبود فیلد هدف نباید خطا بدهد؛ لایه‌های identity/IP همچنان فعال‌اند."""
    throttle = auth_throttles.OTPTargetThrottle()
    assert throttle.get_cache_key(_json_request({}), None) is None


def test_otp_sending_views_carry_all_three_throttle_layers() -> None:
    """endpointهای ارسال OTP باید هر سه محور throttle را همزمان داشته باشند."""
    from apps.authentication import views as auth_views

    otp_sending_views = (
        auth_views.SignupRequestAPIView,
        auth_views.LoginOTPRequestAPIView,
        auth_views.IdentifierAddRequestAPIView,
        auth_views.IdentifierForgotPasswordRequestAPIView,
    )

    for view in otp_sending_views:
        classes = set(view.throttle_classes)
        assert auth_throttles.OTPGlobalIPThrottle in classes, view.__name__
        assert auth_throttles.OTPTargetThrottle in classes, view.__name__


# ===========================================================================
# A5 — زنجیره‌ی هش audit نباید تحت همزمانی منشعب شود
# ===========================================================================


@pytest.mark.django_db
def test_audit_chain_assigns_monotonic_positions() -> None:
    """هر رکورد باید موقعیت بعدی زنجیره و هش قبلی درست را بگیرد."""
    first = create_audit_log(action="A", resource_type="t", resource_id="1")
    second = create_audit_log(action="B", resource_type="t", resource_id="2")

    assert first.chain_index == 1
    assert first.previous_hash == GENESIS_HASH
    assert second.chain_index == 2
    assert second.previous_hash == first.event_hash


@pytest.mark.django_db
def test_audit_chain_recovers_when_losing_the_position_race(monkeypatch) -> None:
    """
    اگر نویسنده‌ی دیگری موقعیت را گرفته باشد، insert باید دوباره لینک شود.

    باگ اصلی: خواندن سر زنجیره بدون قفل انجام می‌شد و دو insert همزمان
    یک previous_hash می‌گرفتند. چون event_hash دو رکورد فرق داشت،
    constraint موجود جلوی انشعاب را نمی‌گرفت و tamper-evidence بی‌صدا
    از بین می‌رفت.
    """
    first = create_audit_log(action="A", resource_type="t", resource_id="1")
    second = create_audit_log(action="B", resource_type="t", resource_id="2")

    real_head = AuditLog._read_chain_head.__func__
    calls = {"count": 0}

    def stale_head_once(cls, *, using):
        calls["count"] += 1
        if calls["count"] == 1:
            # شبیه‌سازی خواندن سر قدیمیِ زنجیره توسط یک نویسنده‌ی موازی
            return {"chain_index": first.chain_index, "event_hash": first.event_hash}
        return real_head(cls, using=using)

    monkeypatch.setattr(AuditLog, "_read_chain_head", classmethod(stale_head_once))

    third = create_audit_log(action="C", resource_type="t", resource_id="3")

    assert calls["count"] == 2, "باید دقیقاً یک بار retry می‌کرد"
    assert third.chain_index == 3
    assert third.previous_hash == second.event_hash
    assert verify_audit_chain_integrity().verified is True


@pytest.mark.django_db
def test_audit_chain_position_is_unique_at_database_level() -> None:
    """انشعاب زنجیره باید در سطح دیتابیس غیرممکن باشد، نه صرفاً بعید."""
    first = create_audit_log(action="A", resource_type="t", resource_id="1")

    forked = AuditLog(
        action="FORK",
        resource_type="t",
        resource_id="9",
        chain_index=first.chain_index,
        previous_hash=GENESIS_HASH,
        event_hash="f" * 64,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        forked.save()


@pytest.mark.django_db
def test_audit_chain_verification_follows_chain_index() -> None:
    """پیمایش verifier باید روی chain_index باشد، نه created_at."""
    for index in range(5):
        create_audit_log(action=f"A{index}", resource_type="t", resource_id=str(index))

    result = verify_audit_chain_integrity()

    assert result.verified is True
    assert result.checked == 5


def test_audit_task_retries_instead_of_swallowing_failures() -> None:
    """
    تسک audit نباید رکورد امنیتی را بی‌صدا دور بیندازد.

    پیکربندی قبلی (max_retries=0 + acks_late=False + swallow) یعنی یک
    قطعی لحظه‌ای دیتابیس یا کشته‌شدن worker حین deploy، رکورد را برای
    همیشه حذف می‌کرد.
    """
    from apps.audit_logs.tasks import create_audit_log_task

    assert create_audit_log_task.max_retries >= 3
    assert create_audit_log_task.acks_late is True
    assert create_audit_log_task.reject_on_worker_lost is True


# ===========================================================================
# A7 — I/O خارجی نباید داخل transaction انجام شود
# ===========================================================================


def _function_body_calls(module, function_name: str) -> set[str]:
    """استخراج نام تمام فراخوانی‌های داخل بدنه‌ی یک تابع (بدون docstring/کامنت)."""
    tree = ast.parse(inspect.getsource(module))
    target = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    names: set[str] = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                names.add(func.attr)
            elif isinstance(func, ast.Name):
                names.add(func.id)
    return names


def _decorator_names(module, function_name: str) -> set[str]:
    """استخراج نام decoratorهای یک تابع سطح ماژول."""
    tree = ast.parse(inspect.getsource(module))
    target = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    names: set[str] = set()
    for decorator in target.decorator_list:
        if isinstance(decorator, ast.Attribute):
            names.add(decorator.attr)
        elif isinstance(decorator, ast.Name):
            names.add(decorator.id)
    return names


def test_initiate_participation_is_not_wrapped_in_a_transaction() -> None:
    """
    فراخوانی درگاه نباید زیر قفل ردیف کمپین انجام شود.

    باگ اصلی: کل تابع با decorator اتمیک پوشانده شده بود و تماس تا ۱۰
    ثانیه‌ای با زرین‌پال در حالی انجام می‌شد که قفل ردیف کمپین نگه داشته
    شده بود؛ یعنی روی یک کمپین داغ مشارکت‌ها کاملاً سریال می‌شدند.
    """
    from apps.madadkar import services

    calls = _function_body_calls(services, "initiate_participation")
    decorators = _decorator_names(services, "initiate_participation")

    assert "atomic" not in decorators, "این تابع نباید decorator اتمیک داشته باشد"
    assert "select_for_update" not in calls, "قفل باید فقط در فاز رزرو جداگانه باشد"
    assert "_reserve_participation_shares" in calls
    assert "_release_reserved_participation" in calls
    assert "request_payment" in calls, "تماس با درگاه باید در همین تابع و خارج از قفل باشد"


def test_generate_and_send_otp_is_not_wrapped_in_a_transaction() -> None:
    """ارسال پیامک/ایمیل نباید داخل یک transaction باز انجام شود."""
    from apps.authentication import otp as otp_module

    calls = _function_body_calls(otp_module, "generate_and_send_otp")
    decorators = _decorator_names(otp_module, "generate_and_send_otp")

    assert "atomic" not in decorators, "این تابع نباید decorator اتمیک داشته باشد"
    assert "_persist_new_otp" in calls
    assert "_discard_undelivered_otp" in calls
    assert "send" in calls, "ارسال باید در همین تابع و خارج از transaction باشد"


@pytest.mark.django_db
def test_failed_gateway_release_frees_reserved_shares(monkeypatch) -> None:
    """
    شکست درگاه باید سهم رزروشده را آزاد کند و تلاش را FAILED ثبت کند.

    وضعیت نهایی از نظر ظرفیت کمپین با rollback قبلی یکسان است، ولی حالا
    رد تلاش ناموفق برای تحلیل تقلب و پشتیبانی باقی می‌ماند.
    """
    from apps.madadkar import services
    from apps.madadkar.choices import ParticipationStatus
    from apps.madadkar.models import Participation
    from tests.factories import PublishedCampaignFactory, UserFactory

    user = UserFactory()
    campaign = PublishedCampaignFactory()
    shares_before = campaign.purchased_shares

    class _BrokenProvider:
        name = "broken"

        def request_payment(self, **kwargs):
            raise RuntimeError("gateway unreachable")

    monkeypatch.setattr(services, "get_payment_provider", lambda *a, **kw: _BrokenProvider())

    with pytest.raises(services.PaymentGatewayError):
        services.initiate_participation(
            campaign=campaign,
            user=user,
            share_count=3,
            callback_url="https://example.com/cb",
        )

    campaign.refresh_from_db()
    participation = Participation.all_objects.get(campaign=campaign, user=user)

    assert participation.status == ParticipationStatus.FAILED
    assert campaign.purchased_shares == shares_before, "سهم رزروشده باید آزاد شده باشد"


@pytest.mark.django_db
def test_failed_otp_delivery_leaves_no_trace(monkeypatch) -> None:
    """شکست ارسال نباید کد جدیدی باقی بگذارد و نباید کد قبلی را باطل کند."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.authentication import otp as otp_module
    from apps.authentication.choices import OTPPurpose
    from apps.authentication.models import OTPCode, PrimaryIdentifierKind

    identifier = "rollback-probe@example.com"
    purpose = OTPPurpose.SIGNUP

    existing = OTPCode.objects.create(
        identifier_kind=PrimaryIdentifierKind.EMAIL,
        identifier_value=identifier,
        purpose=purpose,
        code_hash="x" * 64,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    OTPCode.objects.filter(pk=existing.pk).update(created_at=timezone.now() - timedelta(seconds=61))

    class _FailingProvider:
        def send(self, **kwargs):
            raise otp_module.OTPDeliveryProviderError("panel down")

    monkeypatch.setattr(otp_module, "get_otp_provider", lambda **kwargs: _FailingProvider())

    with pytest.raises(otp_module.OTPDeliveryError):
        otp_module.generate_and_send_otp(
            identifier_kind=PrimaryIdentifierKind.EMAIL,
            identifier_value=identifier,
            purpose=purpose,
        )

    existing.refresh_from_db()
    remaining = OTPCode.objects.filter(identifier_value=identifier, purpose=purpose)

    assert existing.is_used is False
    assert remaining.count() == 1
    assert remaining.first().pk == existing.pk


# ===========================================================================
# A2/A3/A4 — طوفان invalidate کش
# ===========================================================================


def test_no_global_signal_receivers_are_registered() -> None:
    """
    هیچ گیرنده‌ای نباید بدون sender ثبت شود.

    باگ اصلی: پنج اپ عمومی هرکدام دو گیرنده‌ی گلوبال ثبت می‌کردند، پس
    هر .save() یا .delete() روی هر یک از ۹۵ مدل پروژه ده تابع اضافی را
    اجرا می‌کرد.
    """
    for signal, name in ((post_save, "post_save"), (post_delete, "post_delete")):
        global_receivers = [receiver for receiver in signal.receivers if receiver[0][1] is None]
        assert global_receivers == [], f"{name} گیرنده‌ی بدون sender دارد"


@pytest.mark.django_db(transaction=True)
def test_cache_invalidation_is_coalesced_per_transaction(monkeypatch) -> None:
    """
    چند invalidate روی یک domain در یک transaction باید یکی شود.

    باگ اصلی: یک donation باعث ۲۱ بار invalidate کردن namespaceها و ۷
    رویداد outbox می‌شد، پس کش عمومی یک کمپین فعال هرگز warm نمی‌شد.
    """
    import apps.core.cache_invalidation as cache_invalidation

    calls: list[str] = []
    monkeypatch.setattr(cache_invalidation, "cache_delete_namespace", calls.append)

    from apps.core.models import CacheInvalidationEvent

    CacheInvalidationEvent.objects.all().delete()

    with transaction.atomic():
        for _ in range(10):
            cache_invalidation.invalidate_public_domain("madadkar")
        assert calls == [], "invalidate نباید قبل از commit اجرا شود"

    from apps.core.cache_policy import get_cache_policy

    expected_namespaces = list(get_cache_policy("madadkar").backend_namespaces)

    assert sorted(calls) == sorted(expected_namespaces), (
        "۱۰ فراخوانی باید به یک invalidate تبدیل شود"
    )
    assert CacheInvalidationEvent.objects.filter(domain="madadkar").count() == 1


@pytest.mark.django_db(transaction=True)
def test_cache_invalidation_never_runs_before_commit(monkeypatch) -> None:
    """
    rollback نباید کش را invalidate کند و commit باید حتماً بکند.

    باگ اصلی: افزایش نسخه‌ی namespace قبل از commit انجام می‌شد، پس یک
    خواننده‌ی موازی می‌توانست نسخه‌ی جدید را با داده‌ی commit‌نشده پر کند
    و کش تا پایان hard_ttl (تا ۱۵ دقیقه) کهنه بماند.
    """
    import apps.core.cache_invalidation as cache_invalidation

    calls: list[str] = []
    monkeypatch.setattr(cache_invalidation, "cache_delete_namespace", calls.append)

    class _Rollback(Exception):
        """خطای کنترل‌شده برای اجبار rollback."""

    with pytest.raises(_Rollback), transaction.atomic():
        cache_invalidation.invalidate_public_domain("r4j")
        raise _Rollback

    assert calls == [], "rollback نباید هیچ invalidateی اجرا کند"


def test_madadkar_invalidation_list_excludes_redundant_models() -> None:
    """
    مدل‌هایی که از طریق Campaign پوشش داده می‌شوند نباید تکرار شوند.

    هر مسیری که Payment/Participation را تغییر می‌دهد در انتها
    _sync_campaign_counters() و در نتیجه campaign.save() را صدا می‌زند.
    """
    from apps.madadkar.models import Participation, Payment
    from apps.madadkar.signals import PUBLIC_INVALIDATION_MODELS

    assert Payment not in PUBLIC_INVALIDATION_MODELS
    assert Participation not in PUBLIC_INVALIDATION_MODELS


# ===========================================================================
# A6 — کانتینر باید SIGTERM را به فرآیند نهایی برساند
# ===========================================================================


def test_entrypoint_execs_the_final_process() -> None:
    """
    تحویل نهایی کنترل به CMD باید با exec انجام شود.

    باگ اصلی: شاخه‌ی root فرمان را بدون exec از طریق gosu اجرا می‌کرد.
    tini سیگنال را به bash می‌داد و bash آن را به فرزند foreground
    forward نمی‌کند، پس gunicorn هرگز SIGTERM نمی‌گرفت و بعد از مهلت
    داکر با SIGKILL کشته می‌شد — یعنی قطع شدن requestهای در حال پردازش،
    از جمله callback تأیید پرداخت، در هر deploy.
    """
    entrypoint = (PROJECT_ROOT / "entrypoint.sh").read_text(encoding="utf-8")

    assert "exec gosu" in entrypoint, "تحویل نهایی باید با exec gosu باشد"
    assert "exec_as_app_or_fail" in entrypoint

    # مراحل bootstrap باید برگردند، پس helper آن‌ها نباید exec کند.
    bootstrap_helper = entrypoint.split("run_gosu_or_fail() {", 1)[1].split("}", 1)[0]
    assert "exec " not in bootstrap_helper
