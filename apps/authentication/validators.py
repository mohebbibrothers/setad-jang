"""
Identifier Validators — defensive checks beyond normalization.

این ماژول شامل validatorهای سنگین‌تر است که نیاز به lookup در blocklist
یا DNS query دارند. این validators معمولاً فقط در نقاط حساس مثل signup
صدا زده می‌شوند، نه در هر request.

اصول طراحی:
- Pluggable: هر validator pure-ish است (فقط blocklist و DNS).
- Cached: نتیجه DNS MX به مدت 24 ساعت cached می‌شود تا hot path سریع باشد.
- Fail-open در DNS: اگر DNS خودش fail کرد (network issue)، عبور می‌دهد
  ولی log می‌زند. این یک decision آگاهانه است: نمی‌خواهیم disruption موقت
  در network، legit users را block کند.
- Test-friendly: blocklist با lazy loading، در تست‌ها قابل override است.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import dns.exception
import dns.resolver
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

logger = logging.getLogger("apps.authentication")


# ============================================================
# Constants
# ============================================================

_BLOCKLIST_PATH = (
    Path(settings.BASE_DIR)
    / "apps"
    / "authentication"
    / "data"
    / "disposable_email_domains.txt"
)

# Cache namespace برای نتایج MX check
_MX_CACHE_NAMESPACE = "auth:email:mx_check"
_MX_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 ساعت

# Timeout برای DNS query
_DNS_QUERY_TIMEOUT_SECONDS = 5.0

# E.164 phone format
_E164_PATTERN = re.compile(r"^\+\d{10,15}$")


# ============================================================
# Disposable email blocklist (lazy singleton)
# ============================================================


@lru_cache(maxsize=1)
def disposable_email_blocklist() -> frozenset[str]:
    """
    لود blocklist از فایل و نگه‌داری در حافظه به‌صورت frozenset.

    این تابع فقط یک‌بار در طول lifetime process اجرا می‌شود (lru_cache).
    خروجی frozenset است تا O(1) lookup داشته باشیم و immutable باشد.

    Returns:
        frozenset از تمام domainهای disposable که در blocklist هستند.
    """
    if not _BLOCKLIST_PATH.exists():
        logger.warning(
            "Disposable-email blocklist not found at %s; returning empty set.",
            _BLOCKLIST_PATH,
        )
        return frozenset()

    try:
        with _BLOCKLIST_PATH.open("r", encoding="utf-8") as fp:
            domains = {
                line.strip().lower()
                for line in fp
                if line.strip() and not line.startswith("#")
            }
    except OSError as exc:
        logger.exception(
            "Failed to load disposable-email blocklist: %s",
            exc,
        )
        return frozenset()

    logger.info(
        "Disposable-email blocklist loaded: %d domains.",
        len(domains),
    )
    return frozenset(domains)


def reset_blocklist_cache() -> None:
    """
    Reset کردن cache lazy singleton blocklist.

    این تابع فقط برای تست‌ها لازم است — وقتی می‌خواهیم blocklist را با
    یک نسخه‌ی مصنوعی override کنیم.

    نکته: defensive نوشته شده — اگر در تست monkeypatch روی این تابع انجام
    شده باشد، attribute cache_clear ممکن است وجود نداشته باشد، که در
    این صورت silently عبور می‌کنیم.
    """
    clear = getattr(disposable_email_blocklist, "cache_clear", None)
    if callable(clear):
        clear()


# ============================================================
# Email validators
# ============================================================


def _extract_email_domain(email: str) -> str:
    """
    استخراج دامنه از یک ایمیل نرمالایز شده.

    این تابع فرض می‌کند ایمیل قبلاً normalize شده (lowercase, single @).
    اگر ساختار غیرمنتظره داشت، ValidationError raise می‌کند.
    """
    if "@" not in email or email.count("@") != 1:
        raise ValidationError("ساختار ایمیل نامعتبر است.")

    _, _, domain = email.partition("@")
    domain = domain.strip().lower()
    if not domain or "." not in domain:
        raise ValidationError("دامنه ایمیل نامعتبر است.")

    return domain


def validate_email_not_disposable(email: str) -> None:
    """
    بررسی اینکه دامنه‌ی ایمیل در blocklist disposable نباشد.

    Raises:
        ValidationError: اگر دامنه disposable باشد.
    """
    domain = _extract_email_domain(email)
    blocklist = disposable_email_blocklist()

    if domain in blocklist:
        logger.info("Rejected disposable email domain: %s", domain)
        raise ValidationError(
            "استفاده از سرویس‌های ایمیل موقت مجاز نیست. لطفاً از یک ایمیل معتبر استفاده کنید.",
        )


def _check_domain_has_mx_uncached(domain: str) -> bool | None:
    """
    اجرای واقعی DNS MX query (بدون cache).

    Returns:
        True: domain حداقل یک MX record دارد.
        False: domain قطعاً MX ندارد (NXDOMAIN یا NoAnswer).
        None: DNS query خودش fail کرد (timeout, network issue) — fail-open.
    """
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = _DNS_QUERY_TIMEOUT_SECONDS
        resolver.lifetime = _DNS_QUERY_TIMEOUT_SECONDS

        answers = resolver.resolve(domain, "MX")
        return len(answers) > 0

    except dns.resolver.NXDOMAIN:
        logger.info("DNS NXDOMAIN for %s — domain doesn't exist.", domain)
        return False

    except dns.resolver.NoAnswer:
        logger.info("DNS NoAnswer for %s — no MX record.", domain)
        return False

    except (dns.exception.Timeout, dns.resolver.NoNameservers) as exc:
        logger.warning(
            "DNS lookup failed for %s (transient): %s — fail-open.",
            domain,
            exc,
        )
        return None

    except dns.exception.DNSException as exc:
        logger.warning(
            "DNS lookup unexpected error for %s: %s — fail-open.",
            domain,
            exc,
        )
        return None


def validate_email_domain_has_mx(email: str, *, use_cache: bool = True) -> None:
    """
    بررسی اینکه دامنه‌ی ایمیل قابلیت دریافت ایمیل (MX record) دارد.

    Args:
        email: ایمیل نرمالایز شده.
        use_cache: اگر True، از cache 24 ساعته استفاده می‌کند.

    Raises:
        ValidationError: اگر دامنه قطعاً MX ندارد.

    Behavior on transient DNS failure (fail-open):
        اگر DNS خودش fail کرد، عبور می‌دهد ولی در logs ثبت می‌کند.
        این یعنی legit users در disruption موقت block نمی‌شوند.
    """
    domain = _extract_email_domain(email)

    cache_key = f"{_MX_CACHE_NAMESPACE}:{domain}"
    cached_result: bool | None = None

    if use_cache:
        cached_result = cache.get(cache_key)

    if cached_result is None:
        cached_result = _check_domain_has_mx_uncached(domain)
        if use_cache and cached_result is not None:
            cache.set(cache_key, cached_result, timeout=_MX_CACHE_TTL_SECONDS)

    # cached_result == True → معتبر
    # cached_result == False → قطعاً invalid
    # cached_result is None → fail-open (transient DNS issue)
    if cached_result is False:
        raise ValidationError(
            "دامنه ایمیل قابلیت دریافت ایمیل ندارد. لطفاً ایمیل معتبر وارد کنید.",
        )


def validate_email_for_signup(email: str, *, use_mx_cache: bool = True) -> None:
    """
    Composer: تمام validation های signup را با هم اجرا می‌کند.

    این تابع فقط در signup صدا زده می‌شود، نه در هر validation معمولی.

    Raises:
        ValidationError: اگر هر کدام از validations fail شد.
    """
    validate_email_not_disposable(email)
    validate_email_domain_has_mx(email, use_cache=use_mx_cache)


# ============================================================
# Phone validators
# ============================================================


def validate_phone_format(phone: str) -> None:
    """
    بررسی اینکه phone در فرمت E.164 معتبر باشد.

    این تابع فرض می‌کند phone قبلاً normalize شده. کار اضافه‌ای انجام نمی‌دهد
    جز یک sanity check ساده روی فرمت.

    در Phase C این validator با pluggable phone-lookup provider ادغام
    می‌شود تا بتوان VoIP/carrier check هم اضافه کرد.

    Raises:
        ValidationError: اگر phone در فرمت E.164 نباشد.
    """
    if not isinstance(phone, str) or not _E164_PATTERN.match(phone):
        raise ValidationError(
            "فرمت شماره موبایل نامعتبر است (E.164 expected).",
        )
