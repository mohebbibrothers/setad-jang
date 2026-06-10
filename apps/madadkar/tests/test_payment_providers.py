"""
تست‌های Payment Provider Pattern.

پوشش:
- SandboxProvider: request_payment + verify_payment
- ZarinpalProvider: راه‌اندازی + NotImplementedError + ZarinpalNotConfiguredError
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
# ZarinpalProvider — placeholder behavior
# ============================================================


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

    def test_request_payment_raises_not_implemented(self, settings):
        """تا روز اتصال، request_payment نباید فراخوانی شود."""
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()

        with pytest.raises(NotImplementedError):
            provider.request_payment(
                amount=1000,
                description="x",
                callback_url="http://localhost/cb/",
            )

    def test_verify_payment_raises_not_implemented(self, settings):
        """تا روز اتصال، verify_payment نباید فراخوانی شود."""
        settings.MADADKAR_ZARINPAL_MERCHANT_ID = "test-merchant-id"
        provider = ZarinpalProvider()

        with pytest.raises(NotImplementedError):
            provider.verify_payment(authority="x", amount=1000)


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
