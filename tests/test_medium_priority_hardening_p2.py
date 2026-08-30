"""Regression tests for the P2 (yellow) findings — phase 3.

هر کلاس یک یافته را پوشش می‌دهد. هدف این فایل «افزایش پوشش» نیست؛ هدف این
است که هیچ‌کدام از این ده مورد نتوانند بی‌صدا برگردند. جایی که یافته دربارهٔ
*ساختار* کد بوده (مثلاً قانون معماری یا وجود گیت در Makefile)، تست هم در سطح
ساختار نوشته شده و نه فقط رفتار.
"""

from __future__ import annotations

import ast
import re
import time
from pathlib import Path

import pytest
import yaml
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.authentication import anti_abuse, otp as otp_service
from apps.core import cache as core_cache
from apps.core.file_security import (
    DANGEROUS_EXTENSIONS,
    CompositeFileScanner,
    ContentSignatureScanner,
    ExtensionBlocklistScanner,
    get_file_scanner,
    strip_image_metadata,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ============================================================
# 5.1 — architecture rule + list boilerplate
# ============================================================


class TestServiceBackedListPlumbing:
    """یافتهٔ ۵.۱: قانون خام AST و ۵۹ بار تکرار بلوک لیست."""

    def test_serializer_save_is_no_longer_treated_as_db_mutation(self) -> None:
        """ریشهٔ یافته: قانون قبلی `serializer.save()` را ممنوع می‌کرد."""
        from tests.test_architecture_discipline import (
            DJANGO_MANAGER_SEGMENTS,
            VIEW_DB_MUTATION_METHODS,
            _attribute_chain,
        )

        tree = ast.parse("serializer.save()\nThing.objects.create()\n")
        flagged = [
            ".".join(_attribute_chain(node.func))
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in VIEW_DB_MUTATION_METHODS
            and any(seg in DJANGO_MANAGER_SEGMENTS for seg in _attribute_chain(node.func))
        ]
        assert flagged == ["Thing.objects.create"]

    def test_shared_list_helper_exists_with_the_expected_contract(self) -> None:
        from apps.core.views import ServiceBackedListAPIView, paginated_list_response

        assert callable(paginated_list_response)
        assert hasattr(ServiceBackedListAPIView, "get_list_queryset")
        assert ServiceBackedListAPIView.list_pagination_class is not None

    def test_invalid_filter_params_fall_back_to_base_queryset(self) -> None:
        """رفتار فیلتر نامعتبر باید دقیقاً مثل کد قبلی بماند (۴۰۰ نمی‌دهد)."""
        from apps.core.views import apply_filterset

        sentinel = object()
        assert apply_filterset(filterset_class=None, request=None, queryset=sentinel) is sentinel

    def test_duplicated_list_block_is_actually_gone_from_migrated_views(self) -> None:
        """ویوهای مهاجرت‌کرده نباید دیگر paginator را دستی بسازند."""
        # activity کاملاً مهاجرت کرده؛ در بقیه فقط بلوک‌های هم‌شکل جایگزین
        # شده‌اند و ویوهای دارای کش یا منطق خاص عمداً دست‌نخورده مانده‌اند.
        fully_migrated = REPO_ROOT / "apps" / "activity" / "views.py"
        source = fully_migrated.read_text(encoding="utf-8")
        assert "paginator.paginate_queryset" not in source
        assert source.count("paginated_list_response") >= 3

        partially = [
            REPO_ROOT / "apps" / "notifications" / "views.py",
            REPO_ROOT / "apps" / "kindness_wall" / "views.py",
            REPO_ROOT / "apps" / "support_desk",
        ]
        for path in partially:
            # پس از تفکیک P3-16، support_desk/views.py facade است؛ خانوادهٔ
            # views*.py آزمون داده می‌شود (پیامدِ سازگار، نه شل‌شدنِ گیت):
            sources = sorted(path.glob("views*.py")) if path.is_dir() else [path]
            combined = "".join(src.read_text(encoding="utf-8") for src in sources)
            assert "paginated_list_response" in combined, path


# ============================================================
# 5.2 — FORBIDDEN_MARKERS
# ============================================================


class TestTodoPolicy:
    """یافتهٔ ۵.۲: ممنوعیت مطلق TODO، بدهی فنی را پنهان می‌کرد."""

    def test_todo_rule_only_inspects_real_comments(self) -> None:
        """یافتهٔ اصلی: `marker in line` داکسترینگ و رشته را هم می‌گرفت."""
        from tests.test_architecture_discipline import _comment_tokens

        sample = REPO_ROOT / "tests" / "test_architecture_discipline.py"
        comments = _comment_tokens(sample)
        assert all(text.lstrip().startswith("#") for _, text in comments)

    def test_tracked_todo_pattern_requires_an_issue_reference(self) -> None:
        from tests.test_architecture_discipline import TRACKED_TODO_PATTERN

        assert TRACKED_TODO_PATTERN.match("# TODO(#412): بازنویسی این بخش")
        assert TRACKED_TODO_PATTERN.match("# FIXME(#7): نشتی")
        assert not TRACKED_TODO_PATTERN.match("# TODO: بدون شماره")
        assert not TRACKED_TODO_PATTERN.match("# TODO(#412):")

    def test_notimplementederror_is_allowed_again(self) -> None:
        """متد abstract باید بتواند صادقانه NotImplementedError بیندازد."""
        source = (REPO_ROOT / "apps" / "core" / "views.py").read_text(encoding="utf-8")
        assert "NotImplementedError" in source


# ============================================================
# 5.3 — OTP hashing and length
# ============================================================


class TestOtpHardening:
    """یافتهٔ ۵.۳: هش بدون نمک اختصاصی + طول ۵ رقم + ثابت‌های غیرقابل تنظیم."""

    def test_default_code_length_is_six(self, settings) -> None:
        assert otp_service._otp_setting("AUTH_OTP_CODE_LENGTH") == 6
        assert len(otp_service._generate_code()) == 6

    def test_tunables_are_read_at_call_time(self, settings) -> None:
        """ثابت سطح ماژول یعنی نه تست و نه production نمی‌توانند تغییرش دهند."""
        settings.AUTH_OTP_MAX_ATTEMPTS = 9
        settings.AUTH_OTP_TTL_SECONDS = 77
        assert otp_service._otp_setting("AUTH_OTP_MAX_ATTEMPTS") == 9
        assert otp_service._otp_setting("AUTH_OTP_TTL_SECONDS") == 77

    def test_salt_is_unique_per_call(self) -> None:
        salts = {otp_service._generate_salt() for _ in range(50)}
        assert len(salts) == 50
        assert all(len(s) == 32 for s in salts)

    def test_identical_codes_do_not_share_a_hash(self) -> None:
        """هستهٔ یافته: هش نباید فقط تابعی از کد باشد."""
        context = {
            "identifier_kind": "email",
            "identifier_value": "a@example.com",
            "purpose": "signup",
        }
        hashes = {
            otp_service._hash_code("123456", salt=otp_service._generate_salt(), **context)
            for _ in range(20)
        }
        assert len(hashes) == 20

    def test_hash_is_bound_to_identifier_and_purpose(self) -> None:
        base = {"salt": "f" * 32, "identifier_kind": "email"}
        a = otp_service._hash_code("123456", identifier_value="a@x.com", purpose="signup", **base)
        b = otp_service._hash_code("123456", identifier_value="b@x.com", purpose="signup", **base)
        c = otp_service._hash_code("123456", identifier_value="a@x.com", purpose="login", **base)
        assert len({a, b, c}) == 3

    def test_legacy_hash_path_still_verifies_pre_migration_codes(self) -> None:
        """OTPهای در پرواز هنگام deploy نباید یک‌باره نامعتبر شوند."""

        class _LegacyOtp:
            code_salt = ""
            identifier_kind = "email"
            identifier_value = "legacy@example.com"
            purpose = "signup"

        expected = otp_service._hash_code_legacy("12345")
        assert otp_service._expected_hash_for(_LegacyOtp(), "12345") == expected


class TestOtpCooldownRace:
    """باقی‌ماندهٔ فاز ۱: cooldown با الگوی read-then-write مسابقه‌پذیر بود."""

    def test_cooldown_slot_is_claimed_atomically(self) -> None:
        kwargs = {
            "identifier_kind": "email",
            "identifier_value": "race@example.com",
            "purpose": "signup",
        }
        cache.clear()
        assert otp_service._reserve_cooldown_slot(cooldown_seconds=60, **kwargs) is None
        # هر تلاش بعدی در همان پنجره باید رد شود — این همان چیزی است که
        # دو درخواست همزمان را از ساختن دو OTP بازمی‌دارد.
        for _ in range(5):
            remaining = otp_service._reserve_cooldown_slot(cooldown_seconds=60, **kwargs)
            assert remaining is not None and remaining > 0

    def test_releasing_the_slot_allows_a_retry(self) -> None:
        """شکست گذرای provider نباید کاربر را یک دورهٔ کامل قفل کند."""
        kwargs = {
            "identifier_kind": "email",
            "identifier_value": "release@example.com",
            "purpose": "signup",
        }
        cache.clear()
        assert otp_service._reserve_cooldown_slot(cooldown_seconds=60, **kwargs) is None
        otp_service._release_cooldown_slot(**kwargs)
        assert otp_service._reserve_cooldown_slot(cooldown_seconds=60, **kwargs) is None

    def test_cooldown_key_does_not_leak_the_raw_identifier(self) -> None:
        key = otp_service._cooldown_key(
            identifier_kind="phone",
            identifier_value="+989120000000",
            purpose="login",
        )
        assert "+989120000000" not in key


# ============================================================
# 5.4 — dead AUTH_OTP_GLOBAL_THRESHOLD
# ============================================================


class TestGlobalGuardConfiguration:
    """یافتهٔ ۵.۴: تنظیم تعریف‌شده در production.py هرگز خوانده نمی‌شد."""

    def test_threshold_now_comes_from_django_settings(self, settings) -> None:
        settings.AUTH_OTP_GLOBAL_THRESHOLD = 3
        assert anti_abuse._guard_setting("AUTH_OTP_GLOBAL_THRESHOLD") == 3

    def test_module_no_longer_reads_env_directly(self) -> None:
        """خواندن env در زمان import همان چیزی بود که تنظیم را مرده می‌کرد."""
        source = (REPO_ROOT / "apps" / "authentication" / "anti_abuse.py").read_text("utf-8")
        tree = ast.parse(source)
        env_reads = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "config"
        ]
        assert env_reads == []

    def test_defaults_agree_between_base_and_module(self) -> None:
        """اختلاف پیش‌فرض‌ها (۵۰۰ در برابر ۱۰۰۰) نباید دوباره پیش بیاید."""
        from django.conf import settings as django_settings

        assert (
            anti_abuse._GLOBAL_OTP_GUARD_DEFAULTS["AUTH_OTP_GLOBAL_THRESHOLD"]
            == django_settings.AUTH_OTP_GLOBAL_THRESHOLD
        )

    def test_guard_trips_using_the_configured_threshold(self, settings) -> None:
        settings.AUTH_OTP_GLOBAL_THRESHOLD = 2
        settings.AUTH_OTP_GLOBAL_WINDOW_SECONDS = 60
        anti_abuse.reset_global_otp_guard()
        assert anti_abuse.is_global_otp_guard_tripped() is False
        assert anti_abuse.is_global_otp_guard_tripped() is False
        assert anti_abuse.is_global_otp_guard_tripped() is True


# ============================================================
# 5.5 — SWR bugs
# ============================================================


class TestSwrCorrectness:
    """یافتهٔ ۵.۵: سه اشکال ظریف در cache_get_or_set_swr (و یک چهارمی)."""

    def test_lock_is_released_only_after_the_value_is_written(self) -> None:
        """اشکال ۱: آزادسازی قفل قبل از cache.set یک پنجرهٔ dogpile باز می‌گذاشت."""
        key = "setadjang:swrtest:lock-order"
        cache.clear()
        observed: list[bool] = []

        def factory() -> str:
            return "value"

        original_set = cache.set

        def spy_set(k, v, *args, **kwargs):
            if k == key:
                # در لحظهٔ نوشتن مقدار، قفل هنوز باید در اختیار ما باشد.
                observed.append(cache.get(f"{key}:lock") is not None)
            return original_set(k, v, *args, **kwargs)

        cache.set = spy_set
        try:
            core_cache.cache_get_or_set_swr(key=key, factory=factory, soft_ttl=1, hard_ttl=60)
        finally:
            cache.set = original_set

        assert observed == [True]
        assert cache.get(f"{key}:lock") is None

    def test_envelope_timestamp_is_taken_after_the_factory_runs(self) -> None:
        """اشکال ۲: `now` قبل از factory گرفته می‌شد و عمر مقدار کم می‌آمد."""
        key = "setadjang:swrtest:clock"
        cache.clear()

        def slow_factory() -> str:
            time.sleep(0.25)
            return "fresh"

        started = time.time()
        core_cache.cache_get_or_set_swr(key=key, factory=slow_factory, soft_ttl=30, hard_ttl=60)
        envelope = cache.get(key)
        assert envelope["created_at"] >= started + 0.2

    def test_namespace_version_never_resets_to_one_after_eviction(self) -> None:
        """اشکال ۳: evict شدن کلید version باعث سرو شدن دادهٔ خیلی قدیمی می‌شد."""
        namespace = "swrtest:evictable"
        cache.clear()

        first = core_cache.get_namespace_version(namespace)
        core_cache.cache_delete_namespace(namespace)
        bumped = core_cache.get_namespace_version(namespace)
        assert bumped > first

        # شبیه‌سازی eviction تحت فشار حافظه (maxmemory-policy=allkeys-lru).
        cache.delete(f"setadjang:version:{namespace}")
        resurrected = core_cache.get_namespace_version(namespace)

        assert resurrected != 1, "بازگشت به نسخهٔ ۱ یعنی خواندن دوبارهٔ کلیدهای کهنه"
        assert resurrected >= first, "نسخهٔ بازسازی‌شده نباید عقب‌تر از مبنای زمانی باشد"

    def test_cold_miss_path_takes_a_lock(self) -> None:
        """اشکال چهارم (در گزارش نبود): مسیر کش خالی اصلاً قفل نداشت."""
        key = "setadjang:swrtest:cold"
        cache.clear()
        saw_lock: list[bool] = []

        def factory() -> str:
            saw_lock.append(cache.get(f"{key}:lock") is not None)
            return "cold-value"

        result = core_cache.cache_get_or_set_swr(key=key, factory=factory, soft_ttl=30, hard_ttl=60)
        assert result == "cold-value"
        assert saw_lock == [True]

    def test_stale_value_is_served_when_refresh_fails(self) -> None:
        """رفتار fail-open نباید در بازنویسی از دست رفته باشد."""
        key = "setadjang:swrtest:failopen"
        cache.clear()
        core_cache.cache_get_or_set_swr(
            key=key, factory=lambda: "original", soft_ttl=0, hard_ttl=60
        )

        def boom() -> str:
            raise RuntimeError("provider down")

        value = core_cache.cache_get_or_set_swr(key=key, factory=boom, soft_ttl=0, hard_ttl=60)
        assert value == "original"
        assert cache.get(f"{key}:lock") is None, "قفل باید در مسیر خطا هم آزاد شود"


# ============================================================
# 5.6 — file security
# ============================================================


class TestFileSecurity:
    """یافتهٔ ۵.۶: «اسکنر» فقط یک blocklist پسوند ناقص بود."""

    @pytest.mark.parametrize(
        "extension",
        [
            ".htm",
            ".xhtml",
            ".phtml",
            ".php5",
            ".pht",
            ".phar",
            ".jar",
            ".msi",
            ".lnk",
            ".hta",
            ".vbs",
            ".wsf",
        ],
    )
    def test_previously_missing_extensions_are_blocked(self, extension: str) -> None:
        assert extension in DANGEROUS_EXTENSIONS

    def test_default_scanner_is_the_composite_chain(self) -> None:
        assert isinstance(get_file_scanner(), CompositeFileScanner)

    @pytest.mark.parametrize(
        ("filename", "payload", "reason"),
        [
            ("photo.jpg", b"MZ\x90\x00binary", "dos_or_windows_executable"),
            ("resume.pdf", b"\x7fELF\x02\x01payload", "elf_executable"),
            ("notes.txt", b"#!/bin/sh\nrm -rf /", "script_shebang"),
            ("image.jpg", b"<?php system($_GET[0]); ?>", "php_source"),
            ("banner.jpg", b"<html><body>hi</body></html>", "html_document"),
        ],
    )
    def test_renamed_dangerous_content_is_caught_by_signature(
        self, filename: str, payload: bytes, reason: str
    ) -> None:
        """نام فایل حرف کاربر است؛ محتوا واقعیت."""
        result = ContentSignatureScanner().scan(SimpleUploadedFile(filename, payload))
        assert result.clean is False
        assert result.reason == reason

    def test_extension_only_scanner_would_have_missed_these(self) -> None:
        """اثبات اینکه لایهٔ دوم واقعاً چیز تازه‌ای اضافه می‌کند."""
        sneaky = SimpleUploadedFile("photo.jpg", b"MZ\x90\x00binary")
        assert ExtensionBlocklistScanner().scan(sneaky).clean is True
        assert ContentSignatureScanner().scan(sneaky).clean is False

    def test_declared_image_extension_must_match_content(self) -> None:
        mismatch = SimpleUploadedFile("avatar.png", b"\xff\xd8\xff\xe0jpeg-bytes")
        result = ContentSignatureScanner().scan(mismatch)
        assert result.clean is False
        assert result.reason == "content_extension_mismatch"

    def test_legitimate_uploads_still_pass(self) -> None:
        scanner = get_file_scanner()
        assert scanner.scan(SimpleUploadedFile("doc.pdf", b"%PDF-1.4 content")).clean is True
        assert scanner.scan(SimpleUploadedFile("real.png", b"\x89PNG\r\n\x1a\n rest")).clean is True

    def test_scanner_restores_the_file_position(self) -> None:
        """اگر مکان‌نما برنگردد، ذخیره‌سازی بعدی فایل ناقص می‌نویسد."""
        upload = SimpleUploadedFile("real.png", b"\x89PNG\r\n\x1a\n" + b"x" * 100)
        get_file_scanner().scan(upload)
        assert upload.tell() == 0
        assert len(upload.read()) == 108


class TestImageMetadataStripping:
    """یافتهٔ ۵.۶ (بخش حساس): EXIF عکس مدرک، مکان گزارش‌دهنده را لو می‌داد."""

    @staticmethod
    def _jpeg_with_gps() -> bytes:
        from io import BytesIO

        from PIL import Image

        image = Image.new("RGB", (24, 24), (10, 120, 200))
        exif = image.getexif()
        exif[0x8825] = {1: "N", 2: (35.0, 41.0, 0.0), 3: "E", 4: (51.0, 25.0, 0.0)}
        exif[0x010F] = "SecretPhoneBrand"
        buffer = BytesIO()
        image.save(buffer, format="JPEG", exif=exif.tobytes())
        return buffer.getvalue()

    def test_gps_coordinates_are_removed(self) -> None:
        from io import BytesIO

        from PIL import Image

        raw = self._jpeg_with_gps()
        assert 0x8825 in Image.open(BytesIO(raw)).getexif(), "فیکسچر باید واقعاً GPS داشته باشد"

        cleaned = strip_image_metadata(SimpleUploadedFile("evidence.jpg", raw))
        assert cleaned is not None
        after = Image.open(BytesIO(cleaned.read())).getexif()
        assert 0x8825 not in after
        assert len(dict(after)) == 0

    def test_pixels_survive_the_rewrite(self) -> None:
        from io import BytesIO

        from PIL import Image

        cleaned = strip_image_metadata(SimpleUploadedFile("evidence.jpg", self._jpeg_with_gps()))
        red, green, blue = Image.open(BytesIO(cleaned.read())).getpixel((5, 5))
        assert abs(red - 10) < 12 and abs(green - 120) < 12 and abs(blue - 200) < 12

    def test_non_image_uploads_are_left_untouched(self) -> None:
        """این تابع هرگز نباید باعث از دست رفتن یک آپلود معتبر شود."""
        assert strip_image_metadata(SimpleUploadedFile("a.pdf", b"%PDF-1.4")) is None

    def test_model_field_enforces_stripping_on_every_save_path(self) -> None:
        """اجرا در سطح فیلد یعنی ادمین و ایمپورت هم نمی‌توانند دورش بزنند."""
        from apps.core.fields import SanitizedImageField
        from apps.r4j.models import R4JCriminalPhoto

        field = R4JCriminalPhoto._meta.get_field("image")
        assert isinstance(field, SanitizedImageField)


# ============================================================
# 5.7 — upload limits
# ============================================================


class TestUploadLimits:
    """یافتهٔ ۵.۷: سقف حجم فقط بعد از نوشته‌شدن کل فایل بررسی می‌شد."""

    def test_django_level_limits_are_configured(self) -> None:
        from django.conf import settings

        assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 25 * 1024 * 1024
        assert settings.DATA_UPLOAD_MAX_NUMBER_FIELDS == 1000
        assert settings.DATA_UPLOAD_MAX_NUMBER_FILES == 20
        assert settings.FILE_UPLOAD_MAX_MEMORY_SIZE > 0

    def test_request_limit_sits_above_the_attachment_limit(self) -> None:
        """سقف درخواست باید کمی بالاتر باشد وگرنه آپلود معتبر رد می‌شود."""
        from django.conf import settings

        from apps.r4j.validators import ATTACHMENT_MAX_SIZE_BYTES

        assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE > ATTACHMENT_MAX_SIZE_BYTES


# ============================================================
# 5.8 — formatting gate
# ============================================================


class TestFormattingGate:
    """یافتهٔ ۵.۸: تنظیمات فرمت وجود داشت ولی هیچ گیتی اجرایش نمی‌کرد."""

    def test_makefile_exposes_a_format_check_target(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        assert re.search(r"^format-check:", makefile, re.MULTILINE)
        assert "ruff format --check" in makefile

    def test_format_check_is_part_of_the_verify_gate(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        verify_line = next(line for line in makefile.splitlines() if line.startswith("verify:"))
        assert "format-check" in verify_line

    def test_ci_runs_the_format_check(self) -> None:
        workflow = yaml.safe_load(
            (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
        )
        commands = [
            step.get("run", "")
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
        ]
        assert any("format-check" in command for command in commands)


# ============================================================
# 5.9 — dead task and unenforced policy
# ============================================================


class TestScheduledMaintenance:
    """یافتهٔ ۵.۹: تسک مرده و سیاست نگهداشتِ بدون مجری."""

    def test_expire_listings_task_actually_calls_the_service(self) -> None:
        source = (REPO_ROOT / "apps" / "kindness_wall" / "tasks.py").read_text("utf-8")
        assert "expire_due_listings" in source
        assert "Future task hook" not in source, "نسخهٔ stub نباید برگردد"

    @pytest.mark.django_db
    def test_expire_listings_task_expires_due_listings(self) -> None:
        from apps.kindness_wall.choices import ListingStatus
        from apps.kindness_wall.models import KindnessListing
        from apps.kindness_wall.tasks import expire_old_listings_task
        from tests.factories.kindness_wall import PublishedNeedListingFactory

        stale = PublishedNeedListingFactory()
        KindnessListing.objects.filter(pk=stale.pk).update(
            expires_at=timezone.now() - timezone.timedelta(days=1)
        )

        expired = expire_old_listings_task()

        stale.refresh_from_db()
        assert expired >= 1
        assert stale.status == ListingStatus.EXPIRED

    def test_both_tasks_are_routed_and_scheduled(self) -> None:
        from django.conf import settings

        for task_name in (
            "apps.kindness_wall.tasks.expire_old_listings_task",
            "apps.audit_logs.tasks.enforce_audit_retention_task",
        ):
            assert task_name in settings.CELERY_TASK_ROUTES, f"{task_name} route ندارد"
            scheduled = {e["task"] for e in settings.CELERY_BEAT_SCHEDULE.values()}
            assert task_name in scheduled, f"{task_name} در beat نیست"

    @pytest.mark.django_db
    def test_audit_retention_task_is_non_destructive(self) -> None:
        from apps.audit_logs.tasks import enforce_audit_retention_task

        report = enforce_audit_retention_task()
        assert report["destructive_deletion_performed"] is False
        assert "eligible_for_archive_count" in report


# ============================================================
# 5.10 — token lifetime and per-request session query
# ============================================================


class TestSessionValidationCost:
    """یافتهٔ ۵.۱۰: عمر یک‌روزهٔ توکن + یک کوئری DB روی هر درخواست."""

    def test_access_token_lifetime_is_short(self) -> None:
        from datetime import timedelta

        from django.conf import settings

        lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
        assert lifetime <= timedelta(minutes=60)
        assert lifetime < settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]

    @pytest.mark.django_db
    def test_repeated_validation_does_not_hit_the_database(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.authentication.constants import SESSION_ID_CLAIM
        from apps.authentication.models import AuthSession
        from apps.authentication.services import validate_and_touch_session
        from tests.factories import UserFactory

        user = UserFactory()
        session = AuthSession.objects.create(
            user=user, refresh_jti="jti-perf", last_seen_at=timezone.now()
        )
        claims = {SESSION_ID_CLAIM: str(session.pk)}
        cache.clear()

        # اولین فراخوانی کش را پر می‌کند.
        assert validate_and_touch_session(user=user, token_claims=claims) is True

        with CaptureQueriesContext(connection) as ctx:
            for _ in range(10):
                assert validate_and_touch_session(user=user, token_claims=claims) is True
        assert len(ctx.captured_queries) == 0, "بررسی نشست نباید در هر درخواست به DB بزند"

    @pytest.mark.django_db
    def test_revocation_takes_effect_immediately_despite_caching(self) -> None:
        """حیاتی: کش نباید «لغو فوری نشست» را خراب کند."""
        from apps.authentication.constants import SESSION_ID_CLAIM
        from apps.authentication.models import AuthSession
        from apps.authentication.services import revoke_auth_session, validate_and_touch_session
        from tests.factories import UserFactory

        user = UserFactory()
        session = AuthSession.objects.create(
            user=user, refresh_jti="jti-revoke", last_seen_at=timezone.now()
        )
        claims = {SESSION_ID_CLAIM: str(session.pk)}
        cache.clear()

        assert validate_and_touch_session(user=user, token_claims=claims) is True
        revoke_auth_session(session=session)
        assert validate_and_touch_session(user=user, token_claims=claims) is False

    @pytest.mark.django_db
    def test_missing_cache_falls_back_to_the_database(self) -> None:
        """اگر کش در دسترس نباشد، افت کارایی مجاز است — افت امنیت نه."""
        from apps.authentication.constants import SESSION_ID_CLAIM
        from apps.authentication.models import AuthSession
        from apps.authentication.services import validate_and_touch_session
        from tests.factories import UserFactory

        user = UserFactory()
        session = AuthSession.objects.create(
            user=user, refresh_jti="jti-nocache", last_seen_at=timezone.now(), is_revoked=True
        )
        cache.clear()
        assert (
            validate_and_touch_session(user=user, token_claims={SESSION_ID_CLAIM: str(session.pk)})
            is False
        )


# ============================================================
# 5.11 / 5.12 — test layout and generated docs
# ============================================================


class TestRepositoryHygiene:
    """یافتهٔ ۵.۱۱ و ۵.۱۲: نام‌گذاری تست‌ها و اسناد تولیدشدهٔ کهنه."""

    def test_no_test_file_is_named_after_a_development_phase(self) -> None:
        offenders = [
            path.name
            for path in (REPO_ROOT / "tests").glob("test_*.py")
            if re.search(r"_(phase\d+|apex(_[a-d]\d+)?|[a-d]\d+)\.py$", path.name)
        ]
        assert offenders == [], f"نام تست باید دامنه را بگوید نه فاز توسعه: {offenders}"

    def test_app_tests_use_one_consistent_layout(self) -> None:
        """سه الگوی همزمان (پکیج، فایل واحد، ریشه) به یکی کاهش یافت."""
        stray = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in (REPO_ROOT / "apps").glob("*/tests.py")
        ]
        assert stray == [], f"این اپ‌ها باید پکیج tests/ داشته باشند: {stray}"

    def test_structure_document_is_generated_and_current(self) -> None:
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "scripts/generate_structure.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr

    def test_structure_document_lists_every_app(self) -> None:
        """یافتهٔ اصلی: شش اپ در سند غایب بودند."""
        content = (REPO_ROOT / "STRUCTURE.md").read_text(encoding="utf-8")
        for app in (
            "lms",
            "kindness_wall",
            "support_desk",
            "notifications",
            "activity",
            "command_center",
        ):
            assert f"`{app}`" in content, f"{app} در STRUCTURE.md نیست"

    def test_generated_tree_dump_is_no_longer_committed(self) -> None:
        assert not (REPO_ROOT / "project_structure.txt").exists()

    def test_schema_check_detects_drift_not_just_validity(self) -> None:
        """یافتهٔ ۵.۱۲: CI فقط validate می‌کرد و drift بی‌صدا وارد می‌شد."""
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        schema_block = makefile.split("schema-check:")[1].split("\n\n")[0]
        assert "diff" in schema_block

    def test_structure_check_is_wired_into_the_verify_gate(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        verify_line = next(line for line in makefile.splitlines() if line.startswith("verify:"))
        assert "structure-check" in verify_line
