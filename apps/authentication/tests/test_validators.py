"""
Tests — apps.authentication.validators

این تست‌ها contract کامل validators را پوشش می‌دهند:
- email disposable detection (با blocklist مصنوعی)
- MX-record check (با mock کردن dns.resolver)
- composer signup
- phone format validation

اصول طراحی:
- blocklist را با pre-loading فریز شده‌ی lru_cache override می‌کنیم
  تا تست مستقل از فایل واقعی باشد و teardown صحیح کار کند.
- DNS resolver را با monkeypatch روی dns.resolver.Resolver mock می‌کنیم
  تا تست هیچ network call واقعی نزند.
- cache hygiene توسط fixture autouse در conftest انجام می‌شود.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.authentication import validators

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def _reset_blocklist_singleton() -> None:
    """قبل و بعد هر تست، lazy singleton blocklist را reset می‌کنیم."""
    validators.reset_blocklist_cache()
    yield
    validators.reset_blocklist_cache()


@pytest.fixture
def fake_blocklist(monkeypatch: pytest.MonkeyPatch) -> frozenset[str]:
    """
    blocklist مصنوعی شامل چند دامنه‌ی شناخته‌شده‌ی disposable.

    رویکرد:
    - فایل واقعی blocklist را موقتاً به یک مسیر nonexistent منتقل می‌کنیم
      تا lru_cache یک frozenset خالی بسازد.
    - سپس از یک shim استفاده می‌کنیم که آن frozenset را با fake جایگزین کند.

    این روش teardown-safe است چون lru_cache دست‌نخورده می‌ماند.
    """
    fake = frozenset(
        {
            "mailinator.com",
            "tempmail.io",
            "10minutemail.com",
            "guerrillamail.com",
        },
    )

    # روی module-level call را intercept می‌کنیم با یک wrapper که
    # هم cache_clear را به‌درستی delegate می‌کند و هم lazy است.
    class _FakeCacheableFn:
        def __call__(self) -> frozenset[str]:
            return fake

        def cache_clear(self) -> None:
            """no-op برای سازگاری با reset_blocklist_cache."""
            return None

    monkeypatch.setattr(validators, "disposable_email_blocklist", _FakeCacheableFn())
    return fake


class _MXAnswer:
    """شبیه‌ساز یک MX answer ساده برای mock."""

    def __init__(self, count: int = 1) -> None:
        self._count = count

    def __len__(self) -> int:
        return self._count


class _FakeResolver:
    """شبیه‌ساز dns.resolver.Resolver با رفتار قابل پیکربندی."""

    def __init__(self) -> None:
        self.timeout = 5.0
        self.lifetime = 5.0
        self._behavior: str = "ok"

    def configure(self, behavior: str) -> None:
        """
        behavior یکی از این مقادیر:
        - "ok": دامنه MX دارد
        - "nxdomain": دامنه وجود ندارد
        - "noanswer": دامنه هست ولی MX ندارد
        - "timeout": DNS timeout
        - "nameserver_fail": هیچ nameserver جواب نداد
        """
        self._behavior = behavior

    def resolve(self, domain: str, record_type: str):
        import dns.exception
        import dns.resolver

        if self._behavior == "ok":
            return _MXAnswer(count=2)
        if self._behavior == "nxdomain":
            raise dns.resolver.NXDOMAIN
        if self._behavior == "noanswer":
            raise dns.resolver.NoAnswer
        if self._behavior == "timeout":
            raise dns.exception.Timeout
        if self._behavior == "nameserver_fail":
            raise dns.resolver.NoNameservers

        raise dns.exception.DNSException("unexpected behavior")


@pytest.fixture
def fake_dns_resolver(monkeypatch: pytest.MonkeyPatch) -> _FakeResolver:
    """جایگزینی dns.resolver.Resolver با FakeResolver قابل پیکربندی."""
    fake = _FakeResolver()
    monkeypatch.setattr(
        "dns.resolver.Resolver",
        lambda: fake,
    )
    return fake


# ============================================================
# validate_email_not_disposable
# ============================================================


class TestValidateEmailNotDisposable:
    """ایمیل با دامنه‌ی disposable باید reject شود."""

    def test_rejects_disposable_domain(self, fake_blocklist) -> None:
        with pytest.raises(ValidationError, match="ایمیل موقت"):
            validators.validate_email_not_disposable("attacker@mailinator.com")

    def test_accepts_legitimate_domain(self, fake_blocklist) -> None:
        # نباید raise کند
        validators.validate_email_not_disposable("user@gmail.com")
        validators.validate_email_not_disposable("user@protonmail.com")

    @pytest.mark.parametrize(
        "invalid_email",
        [
            "no-at-sign",
            "double@@at.com",
            "user@",
            "user@nodot",
        ],
    )
    def test_rejects_malformed_email(self, fake_blocklist, invalid_email: str) -> None:
        with pytest.raises(ValidationError):
            validators.validate_email_not_disposable(invalid_email)


# ============================================================
# validate_email_domain_has_mx
# ============================================================


class TestValidateEmailDomainHasMx:
    """بررسی DNS MX با fake resolver."""

    def test_accepts_when_domain_has_mx(self, fake_dns_resolver: _FakeResolver) -> None:
        fake_dns_resolver.configure("ok")
        validators.validate_email_domain_has_mx(
            "user@example.com", use_cache=False
        )

    def test_rejects_when_domain_nxdomain(self, fake_dns_resolver: _FakeResolver) -> None:
        fake_dns_resolver.configure("nxdomain")
        with pytest.raises(ValidationError, match="دامنه ایمیل"):
            validators.validate_email_domain_has_mx(
                "user@nonexistent.example", use_cache=False
            )

    def test_rejects_when_domain_no_mx(self, fake_dns_resolver: _FakeResolver) -> None:
        fake_dns_resolver.configure("noanswer")
        with pytest.raises(ValidationError, match="دامنه ایمیل"):
            validators.validate_email_domain_has_mx(
                "user@nomx.example", use_cache=False
            )

    def test_fails_open_on_dns_timeout(self, fake_dns_resolver: _FakeResolver) -> None:
        """در صورت DNS timeout، باید عبور دهد (fail-open)."""
        fake_dns_resolver.configure("timeout")
        # نباید raise کند
        validators.validate_email_domain_has_mx(
            "user@example.com", use_cache=False
        )

    def test_fails_open_on_nameserver_failure(
        self, fake_dns_resolver: _FakeResolver
    ) -> None:
        """در صورت ناتوانی nameserver، باید عبور دهد."""
        fake_dns_resolver.configure("nameserver_fail")
        validators.validate_email_domain_has_mx(
            "user@example.com", use_cache=False
        )


# ============================================================
# validate_email_for_signup (composer)
# ============================================================


class TestValidateEmailForSignup:
    """composer که هر دو validation را با هم اجرا می‌کند."""

    def test_rejects_disposable_even_if_dns_ok(
        self,
        fake_blocklist,
        fake_dns_resolver: _FakeResolver,
    ) -> None:
        fake_dns_resolver.configure("ok")
        with pytest.raises(ValidationError, match="ایمیل موقت"):
            validators.validate_email_for_signup(
                "attacker@mailinator.com", use_mx_cache=False
            )

    def test_rejects_if_dns_says_no_mx(
        self,
        fake_blocklist,
        fake_dns_resolver: _FakeResolver,
    ) -> None:
        fake_dns_resolver.configure("nxdomain")
        with pytest.raises(ValidationError, match="دامنه ایمیل"):
            validators.validate_email_for_signup(
                "user@nonexistent.example", use_mx_cache=False
            )

    def test_accepts_legitimate_email(
        self,
        fake_blocklist,
        fake_dns_resolver: _FakeResolver,
    ) -> None:
        fake_dns_resolver.configure("ok")
        # نباید raise کند
        validators.validate_email_for_signup(
            "real.user@gmail.com", use_mx_cache=False
        )


# ============================================================
# validate_phone_format
# ============================================================


class TestValidatePhoneFormat:
    """E.164 phone format check."""

    @pytest.mark.parametrize(
        "phone",
        [
            "+989120000000",
            "+12025551234",
            "+442071838750",
        ],
    )
    def test_accepts_valid_e164(self, phone: str) -> None:
        # نباید raise کند
        validators.validate_phone_format(phone)

    @pytest.mark.parametrize(
        "phone",
        [
            "09120000000",  # local، نه E.164
            "9120000000",  # بدون +
            "+12345",  # خیلی کوتاه
            "+" + "9" * 20,  # خیلی طولانی
            "+98abc123",  # کاراکتر invalid
            "",
        ],
    )
    def test_rejects_non_e164(self, phone: str) -> None:
        with pytest.raises(ValidationError):
            validators.validate_phone_format(phone)

    def test_rejects_non_string(self) -> None:
        with pytest.raises(ValidationError):
            validators.validate_phone_format(None)  # type: ignore[arg-type]
