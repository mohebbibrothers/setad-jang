"""
تست‌های Payment Provider Pattern.

پوشش:
- SandboxProvider: request_payment + verify_payment
- ZarinpalProvider: request/verify واقعی با mock شبکه + ZarinpalNotConfiguredError
- Factory: get_payment_provider() + UnknownPaymentProviderError + override
- Result dataclasses: immutability و فیلدهای پیش‌فرض
"""

from __future__ import annotations

import pytest

from apps.madadkar.payment_providers import (
    PaymentRequestResult,
    PaymentVerifyResult,
    SandboxProvider,
    UnknownPaymentProviderError,
    ZarinpalNotConfiguredError,
    ZarinpalProvider,
    get_payment_provider,
)

# ============================================================
# SandboxProvider
# ============================================================


class TestSandboxProviderRequest:
    """تست‌های SandboxProvider.request_payment"""

    def test_request_payment_returns_success(self):
        provider = SandboxProvider()
        result = provider.request_payment(
            amount=50_000_000,
            description="تست",
            callback_url="http://localhost/api/v1/madadkar/payment/verify/",
        )

        assert result.success is True
        assert result.authority
        assert result.authority.startswith("SBX-")
        assert result.gateway_url
        assert "authority=" in result.gateway_url
        assert result.gateway_status == "100"

    def test_request_payment_includes_authority_in_url(self):
        provider = SandboxProvider()
        result = provider.request_payment(
            amount=10_000_000,
            description="تست",
            callback_url="http://localhost/cb/",
        )
        assert result.authority in result.gateway_url

    def test_request_payment_includes_amount_in_url(self):
        provider = SandboxProvider()
        result = provider.request_payment(
            amount=99_000_000,
            description="تست",
            callback_url="http://localhost/cb/",
        )
        assert "amount=99000000" in result.gateway_url

    def test_request_payment_each_call_returns_unique_authority(self):
        """هر فراخوانی authority جدید تولید می‌کند."""
        provider = SandboxProvider()
        a = provider.request_payment(
            amount=1000,
            description="x",
            callback_url="http://localhost/cb/",
        )
        b = provider.request_payment(
            amount=1000,
            description="x",
            callback_url="http://localhost/cb/",
        )
        assert a.authority != b.authority

    def test_request_payment_metadata_stored_in_extra(self):
        provider = SandboxProvider()
        result = provider.request_payment(
            amount=1000,
            description="x",
            callback_url="http://localhost/cb/",
            mobile="09120000000",
            email="u@x.com",
            metadata={"campaign_id": "7"},
        )
        assert result.extra["mobile"] == "09120000000"
        assert result.extra["email"] == "u@x.com"
        assert result.extra["metadata"] == {"campaign_id": "7"}


class TestSandboxProviderVerify:
    """تست‌های SandboxProvider.verify_payment"""

    def test_verify_payment_always_returns_success(self):
        provider = SandboxProvider()
        result = provider.verify_payment(
            authority="SBX-test-123",
            amount=50_000_000,
        )
        assert result.success is True
        assert result.already_verified is False
        assert result.ref_id.startswith("SBXREF-")
        assert result.verified_amount == 50_000_000
        assert result.gateway_status == "100"

    def test_verify_payment_returns_same_amount(self):
        """sandbox همیشه amount ورودی را verify می‌کند (anti-tampering pass)."""
        provider = SandboxProvider()
        result = provider.verify_payment(
            authority="any",
            amount=123_456_789,
        )
        assert result.verified_amount == 123_456_789

    def test_verify_payment_ref_id_unique_per_call(self):
        provider = SandboxProvider()
        a = provider.verify_payment(authority="x", amount=1)
        b = provider.verify_payment(authority="x", amount=1)
        assert a.ref_id != b.ref_id


# ============================================================
# ZarinpalProvider — HTTP integration behavior
# ============================================================


class _FakeZarinpalResponse:
    """Response کوچک و deterministic برای mock کردن POST در تست‌های زرین‌پال."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: dict | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(self._payload)

    def json(self):
        """برگرداندن payload mock‌شده مشابه requests.Response.json."""
        return self._payload


def _patch_gateway_post(monkeypatch, fake_post) -> None:
    """جایگزینی POST درگاه با یک fake.

    provider حالا از یک `requests.Session` مشترک و pool-شده استفاده می‌کند
    (به‌جای `requests.post` سراسری) تا برای هر پرداخت TLS handshake تازه
    باز نشود. پس تست‌ها هم باید همان Session را هدف بگیرند.

    یک stub سبک تزریق می‌شود تا امضای `fake_post(url, *, json, timeout)`
    در تست‌ها دست‌نخورده بماند و هیچ Session واقعی‌ای ساخته نشود.
    """

    class _StubSession:
        post = staticmethod(fake_post)

    monkeypatch.setattr(
        "apps.madadkar.payment_providers.zarinpal._get_session",
        lambda: _StubSession(),
    )


class TestZarinpalProviderConfiguration:
    """تست‌های پیکربندی ZarinpalProvider"""

    def test_raises_when_merchant_id_empty(self, settings):
        """بدون merchant_id نباید instantiate شود."""
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = ""

        with pytest.raises(ZarinpalNotConfiguredError):
            ZarinpalProvider()

    def test_instantiates_when_merchant_id_present(self, settings):
        """با merchant_id باید موفق instantiate شود."""
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()
        assert provider.merchant_id == "test-merchant-id"

    def test_uses_sandbox_urls_when_sandbox_enabled(self, settings):
        """در حالت sandbox endpointها باید sandbox باشند."""
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        settings.MADADKAR_ZARINPAL_SANDBOX = True

        provider = ZarinpalProvider()

        assert "sandbox.zarinpal.com" in provider.request_url
        assert "sandbox.zarinpal.com" in provider.verify_url
        assert "sandbox.zarinpal.com" in provider.startpay_url_template

    def test_uses_production_urls_when_sandbox_disabled(self, settings):
        """در حالت production endpointها نباید sandbox باشند."""
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        settings.MADADKAR_ZARINPAL_SANDBOX = False

        provider = ZarinpalProvider()

        assert provider.request_url == ZarinpalProvider.REQUEST_URL
        assert provider.verify_url == ZarinpalProvider.VERIFY_URL
        assert provider.startpay_url_template == ZarinpalProvider.STARTPAY_URL


class TestZarinpalProviderRequestPayment:
    """تست‌های request_payment زرین‌پال با mock شبکه."""

    def test_request_payment_success_returns_authority_and_gateway_url(
        self,
        settings,
        monkeypatch,
    ):
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()
        calls = []

        def fake_post(url, json, timeout):
            calls.append({"url": url, "json": json, "timeout": timeout})
            return _FakeZarinpalResponse(
                payload={"data": {"code": 100, "authority": "A0000000000001"}, "errors": []}
            )

        _patch_gateway_post(monkeypatch, fake_post)

        result = provider.request_payment(
            amount=1000,
            description="کمک",
            callback_url="https://example.com/callback",
            mobile="09120000000",
            email="user@example.com",
            metadata={"campaign_id": "7"},
        )

        assert result.success is True
        assert result.authority == "A0000000000001"
        assert result.gateway_status == "100"
        assert result.authority in result.gateway_url
        assert calls[0]["timeout"] == provider.REQUEST_TIMEOUT_SECONDS
        assert calls[0]["json"]["merchant_id"] == "test-merchant-id"
        assert calls[0]["json"]["metadata"]["mobile"] == "09120000000"
        assert calls[0]["json"]["metadata"]["campaign_id"] == "7"

    def test_request_payment_converts_toman_to_rial_for_gateway(self, settings, monkeypatch):
        """Regression (ممیزی ۱۴۰۴-۰۶-۱۰): واحد وجهی زرین‌پال ریال است.

        ارسال مستقیم مبلغِ تومان یعنی کاربر یک‌دهم مبلغ واقعی را در درگاه
        پرداخت می‌کند و verify هم (به‌همان نسبت اشتباه) سبز درمی‌آید. تبدیل
        باید در مرز provider انجام شود.
        """
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()
        calls = []

        def fake_post(url, json, timeout):
            calls.append(json)
            return _FakeZarinpalResponse(
                payload={"data": {"code": 100, "authority": "A0000000000001"}, "errors": []}
            )

        _patch_gateway_post(monkeypatch, fake_post)

        provider.request_payment(
            amount=12_500,
            description="کمک",
            callback_url="https://example.com/callback",
        )

        assert calls[0]["amount"] == 125_000

    def test_request_payment_gateway_error_returns_failure(self, settings, monkeypatch):
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()

        def fake_post(url, json, timeout):
            return _FakeZarinpalResponse(
                payload={"data": {"code": -9}, "errors": {"message": "invalid merchant"}}
            )

        _patch_gateway_post(monkeypatch, fake_post)

        result = provider.request_payment(
            amount=1000,
            description="کمک",
            callback_url="https://example.com/callback",
        )

        assert result.success is False
        assert result.gateway_status == "-9"
        assert result.error_message == "invalid merchant"

    def test_request_payment_timeout_returns_structured_failure(self, settings, monkeypatch):
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()

        def fake_post(url, json, timeout):
            raise TimeoutError

        import requests

        def fake_timeout(url, json, timeout):
            raise requests.exceptions.Timeout

        _patch_gateway_post(monkeypatch, fake_timeout)

        result = provider.request_payment(
            amount=1000,
            description="کمک",
            callback_url="https://example.com/callback",
        )

        assert result.success is False
        assert result.gateway_status == "transport_error"
        assert "زمان مقرر" in result.error_message


class TestZarinpalProviderVerifyPayment:
    """تست‌های verify_payment زرین‌پال با mock شبکه."""

    def test_verify_payment_success_returns_ref_id_and_amount(self, settings, monkeypatch):
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()
        calls = []

        def fake_post(url, json, timeout):
            calls.append({"url": url, "json": json, "timeout": timeout})
            return _FakeZarinpalResponse(
                payload={"data": {"code": 100, "ref_id": 987654321}, "errors": []}
            )

        _patch_gateway_post(monkeypatch, fake_post)

        result = provider.verify_payment(authority="A0000000000001", amount=2500)

        assert result.success is True
        assert result.already_verified is False
        assert result.ref_id == "987654321"
        assert result.verified_amount == 2500
        assert result.gateway_status == "100"
        assert calls[0]["json"]["authority"] == "A0000000000001"
        assert calls[0]["timeout"] == provider.VERIFY_TIMEOUT_SECONDS

    def test_verify_payment_converts_toman_to_rial_and_keeps_internal_unit(
        self, settings, monkeypatch
    ):
        """verify هم با ریال صدا می‌شود؛ verified_amount همچنان تومان است."""
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()
        calls = []

        def fake_post(url, json, timeout):
            calls.append(json)
            return _FakeZarinpalResponse(
                payload={"data": {"code": 100, "ref_id": 123}, "errors": []}
            )

        _patch_gateway_post(monkeypatch, fake_post)

        result = provider.verify_payment(authority="A1", amount=12_500)

        assert calls[0]["amount"] == 125_000
        assert result.verified_amount == 12_500

    def test_verify_payment_code_101_is_idempotent_success(self, settings, monkeypatch):
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()

        def fake_post(url, json, timeout):
            return _FakeZarinpalResponse(
                payload={"data": {"code": 101, "ref_id": "REF-101"}, "errors": []}
            )

        _patch_gateway_post(monkeypatch, fake_post)

        result = provider.verify_payment(authority="A0000000000001", amount=2500)

        assert result.success is True
        assert result.already_verified is True
        assert result.ref_id == "REF-101"
        assert result.gateway_status == "101"

    def test_verify_payment_gateway_error_returns_failure(self, settings, monkeypatch):
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()

        def fake_post(url, json, timeout):
            return _FakeZarinpalResponse(
                payload={"data": {"code": -51}, "errors": {"message": "payment not found"}}
            )

        _patch_gateway_post(monkeypatch, fake_post)

        result = provider.verify_payment(authority="bad", amount=2500)

        assert result.success is False
        assert result.gateway_status == "-51"
        assert result.error_message == "payment not found"


# ============================================================
# Factory — get_payment_provider
# ============================================================


class TestGetPaymentProvider:
    """تست‌های factory function"""

    def test_default_returns_sandbox_in_test_settings(self, settings):
        """settings تست باید sandbox باشد (پیش‌فرض)."""
        settings.MADADKAR_PAYMENT_PROVIDER = "sandbox"
        provider = get_payment_provider()
        assert isinstance(provider, SandboxProvider)
        assert provider.name == "sandbox"

    def test_explicit_name_override(self, settings):
        """می‌توان name را به‌صورت explicit پاس داد."""
        provider = get_payment_provider(name="sandbox")
        assert isinstance(provider, SandboxProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(UnknownPaymentProviderError):
            get_payment_provider(name="nonexistent-provider")

    def test_name_is_normalized_lowercase(self):
        provider = get_payment_provider(name="SANDBOX")
        assert isinstance(provider, SandboxProvider)

    def test_zarinpal_resolved_when_configured(self, settings):
        """با merchant_id صحیح، zarinpal باید resolve شود."""
        settings.MADADKAR_PAYMENT_PROVIDER = "zarinpal"
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"

        provider = get_payment_provider()
        assert isinstance(provider, ZarinpalProvider)

    def test_zarinpal_raises_when_not_configured(self, settings):
        settings.MADADKAR_PAYMENT_PROVIDER = "zarinpal"
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = ""

        with pytest.raises(ZarinpalNotConfiguredError):
            get_payment_provider()


# ============================================================
# Result dataclasses
# ============================================================


class TestPaymentRequestResult:
    """تست‌های dataclass PaymentRequestResult"""

    def test_minimal_construction(self):
        result = PaymentRequestResult(success=True, authority="abc")
        assert result.success is True
        assert result.authority == "abc"
        assert result.gateway_url == ""
        assert result.gateway_status == ""
        assert result.error_message == ""
        assert result.extra == {}

    def test_immutability(self):
        """frozen=True یعنی modify ممنوع است."""
        result = PaymentRequestResult(success=True, authority="abc")
        with pytest.raises((AttributeError, Exception)):
            result.authority = "different"

    def test_failure_result(self):
        result = PaymentRequestResult(
            success=False,
            error_message="درگاه در دسترس نیست",
        )
        assert result.success is False
        assert result.authority == ""
        assert result.error_message == "درگاه در دسترس نیست"


class TestPaymentVerifyResult:
    """تست‌های dataclass PaymentVerifyResult"""

    def test_minimal_construction(self):
        result = PaymentVerifyResult(success=True)
        assert result.success is True
        assert result.already_verified is False
        assert result.ref_id == ""
        assert result.verified_amount == 0

    def test_full_construction(self):
        result = PaymentVerifyResult(
            success=True,
            already_verified=True,
            ref_id="REF-123",
            verified_amount=50_000_000,
            gateway_status="101",
        )
        assert result.already_verified is True
        assert result.verified_amount == 50_000_000

    def test_immutability(self):
        result = PaymentVerifyResult(success=True)
        with pytest.raises((AttributeError, Exception)):
            result.success = False
