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
    """تست‌های SandboxProvider.request_payment — درگاه تعاملی sandbox."""

    def test_request_payment_returns_success(self, settings):
        settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL = "http://gateway.test"
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
        assert result.gateway_status == "100"

    def test_gateway_url_is_sandbox_page_not_callback(self, settings):
        settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL = "http://gateway.test"
        """باگ رگرسیونی ۱۴۰۵/۷: gateway_url نباید خودِ callback verify باشد.

        اگر verify مستقیم در URL باشد، «ادامه» در فرانت بدون هیچ تعاملی
        تراکنش را SUCCESS می‌کرد (پرداخت ساختگی). باید به صفحهٔ تعاملی
        sandbox برود و مبلغ هرگز در query نباشد (منبع حقیقت = DB).
        """
        provider = SandboxProvider()
        result = provider.request_payment(
            amount=10_000_000,
            description="تست",
            callback_url="http://localhost/api/v1/madadkar/payment/verify/",
        )
        assert (
            result.gateway_url
            == f"http://gateway.test/api/v1/madadkar/payment/sandbox/{result.authority}/"
        )
        assert "verify" not in result.gateway_url
        assert "amount" not in result.gateway_url

    def test_request_payment_includes_authority_in_url(self, settings):
        settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL = "http://gateway.test"
        provider = SandboxProvider()
        result = provider.request_payment(
            amount=10_000_000,
            description="تست",
            callback_url="http://localhost/cb/",
        )
        assert result.authority in result.gateway_url

    def test_request_payment_each_call_returns_unique_authority(self, settings):
        settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL = "http://gateway.test"
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

    def test_request_payment_metadata_stored_in_extra(self, settings):
        settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL = "http://gateway.test"
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


@pytest.mark.django_db
class TestSandboxProviderVerify:
    """تست‌های SandboxProvider.verify_payment — gated روی تأیید صفحهٔ درگاه.

    رفتار جدید (رگرسیون باگ «پرداخت بدون پول»): verify بدون اینکه کاربر
    در صفحهٔ شبیه‌ساز «تأیید پرداخت» را زده باشد (marker روی رکورد)
    هرگز success نمی‌دهد.
    """

    def test_verify_without_confirmation_fails(self):
        """بدون تأیید در صفحهٔ درگاه → success=False (نه success کور!)."""
        from apps.madadkar.choices import PaymentStatus
        from apps.madadkar.models import Payment
        from tests.factories.madadkar import ParticipationFactory

        participation = ParticipationFactory()
        payment = Payment.objects.create(
            participation=participation,
            user=participation.user,
            amount=50_000_000,
            gateway_name="sandbox",
            authority="SBX-unconfirmed-1",
            status=PaymentStatus.PENDING,
        )
        provider = SandboxProvider()
        result = provider.verify_payment(authority=payment.authority, amount=payment.amount)
        assert result.success is False
        assert "تأیید" in (result.error_message or "")

    def test_verify_unknown_authority_fails(self):
        """authority ناموجود هم دیگر هرگز success ساختگی نمی‌گیرد."""
        provider = SandboxProvider()
        result = provider.verify_payment(authority="SBX-does-not-exist", amount=1)
        assert result.success is False

    def test_verify_after_confirmation_succeeds_with_recorded_amount(self):
        """بعد از confirm سمت سرور → success با مبلغِ خودِ رکورد."""
        from apps.madadkar.choices import PaymentStatus
        from apps.madadkar.models import Payment
        from apps.madadkar.services import confirm_sandbox_payment
        from tests.factories.madadkar import ParticipationFactory

        participation = ParticipationFactory()
        payment = Payment.objects.create(
            participation=participation,
            user=participation.user,
            amount=123_456_789,
            gateway_name="sandbox",
            authority="SBX-confirmed-1",
            status=PaymentStatus.PENDING,
        )
        assert confirm_sandbox_payment(payment=payment) is True

        provider = SandboxProvider()
        result = provider.verify_payment(authority=payment.authority, amount=payment.amount)
        assert result.success is True
        assert result.already_verified is False
        assert result.ref_id.startswith("SBXREF-")
        assert result.verified_amount == 123_456_789
        assert result.gateway_status == "100"

    def test_zarinpal_payment_cannot_be_confirmed_via_sandbox_marker(self):
        """gateway_name غیر sandbox هرگز marker نمی‌گیرد (کارکرد امن service)."""
        from apps.madadkar.choices import PaymentStatus
        from apps.madadkar.models import Payment
        from apps.madadkar.services import confirm_sandbox_payment
        from tests.factories.madadkar import ParticipationFactory

        participation = ParticipationFactory()
        payment = Payment.objects.create(
            participation=participation,
            user=participation.user,
            amount=10_000,
            gateway_name="zarinpal",
            authority="ZAR-real-1",
            status=PaymentStatus.PENDING,
        )
        assert confirm_sandbox_payment(payment=payment) is False
        payment.refresh_from_db()
        assert payment.gateway_status != "SANDBOX-CONFIRMED"


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
