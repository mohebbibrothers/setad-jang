"""
تست‌های صفحهٔ شبیه‌ساز درگاه sandbox + گارد production.

رگرسیون باگ کاربری ۱۴۰۵/۷:
«ادامه» در فرانت مستقیم به /payment/verify/?authority=SBX-…&sandbox=1 می‌رفت
و بدون هیچ پرداختی، تراکنش PAID + رسید می‌شد. اصلاح سه‌لایه:

1. gateway_url حالا صفحهٔ تعاملیِ بک‌اند است (دکمهٔ تأیید/انصراف).
2. SandboxProvider.verify_payment فقط با marker تأییدِ سمت سرور success
   می‌دهد — verify مستقیم/بوکمارک/اسکنر دیگر پرداخت ساختگی تولید نمی‌کند.
3. config/settings/production.py با provider=sandbox اصلاً boot نمی‌شود.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.madadkar.choices import ParticipationStatus, PaymentStatus
from apps.madadkar.models import Participation
from apps.madadkar.payment_providers import SandboxProvider
from tests.factories import UserFactory
from tests.factories.madadkar import PublishedCampaignFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _gateway_url(payment) -> str:
    return reverse("madadkar:payment-sandbox-gateway", kwargs={"authority": payment.authority})


def _initiate_unconfirmed(*, campaign, user, share_count: int = 1):
    """مشارکت تا لحظهٔ دریافت gateway_url — بدون تأیید در صفحهٔ درگاه."""
    client = APIClient()
    client.force_authenticate(user=user)
    with patch(_AUDIT_TASK_PATH):
        response = client.post(
            reverse("madadkar:user-participate", kwargs={"slug": campaign.slug}),
            data={"share_count": share_count},
            format="json",
        )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    body = response.json()["data"]
    payment = Participation.objects.get(user=user, campaign=campaign).payment
    return client, payment, body


class TestSandboxGatewayRedirectContract:
    """gateway_url باید خودِ صفحهٔ درگاه باشد، نه callback verify."""

    def test_participate_response_gateway_url_points_at_page(self):
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        _client, payment, body = _initiate_unconfirmed(campaign=campaign, user=user)

        assert "/payment/sandbox/" in body["gateway_url"]
        assert payment.authority in body["gateway_url"]
        assert "verify" not in body["gateway_url"]

    def test_provider_gateway_url_follows_callback_base(self, settings):
        settings.MADADKAR_PAYMENT_CALLBACK_BASE_URL = "http://api.test"
        provider = SandboxProvider()
        result = provider.request_payment(
            amount=1,
            description="d",
            callback_url="http://api.test/api/v1/madadkar/payment/verify/",
        )
        assert result.gateway_url == (
            f"http://api.test/api/v1/madadkar/payment/sandbox/{result.authority}/"
        )


class TestSandboxGatewayPage:
    """خودِ صفحه: مبلغ از DB (نه query)، ۴۰۴ برای authority نامعتبر."""

    def test_page_renders_amount_from_db_not_query(self):
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        client, payment, _body = _initiate_unconfirmed(
            campaign=campaign,
            user=user,
            share_count=3,
        )
        # amount تحریف‌شده در query هیچ اثری ندارد — منبع حقیقت DB است
        resp = client.get(_gateway_url(payment), {"amount": 1})
        assert resp.status_code == status.HTTP_200_OK
        html = resp.content.decode()
        assert f"{payment.amount:,}" in html
        assert payment.amount != 1
        assert campaign.title in html
        assert "تأیید پرداخت" in html
        assert "انصراف" in html

    def test_unknown_authority_returns_404(self):
        resp = APIClient().get(
            reverse("madadkar:payment-sandbox-gateway", kwargs={"authority": "SBX-nope"}),
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_zarinpal_payment_page_not_served(self):
        """صفحه فقط برای تراکنش sandbox است؛ تراکنش واقعی 404 می‌گیرد."""
        from apps.madadkar.models import Payment
        from tests.factories.madadkar import ParticipationFactory

        p = ParticipationFactory()
        payment = Payment.objects.create(
            participation=p,
            user=p.user,
            amount=5,
            gateway_name="zarinpal",
            authority="ZAR-page-1",
            status=PaymentStatus.PENDING,
        )
        resp = APIClient().get(_gateway_url(payment))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_success_payment_page_is_informational_only(self):
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        client, payment, _body = _initiate_unconfirmed(campaign=campaign, user=user)
        client.post(_gateway_url(payment), data={"action": "confirm"})
        with patch(_AUDIT_TASK_PATH):
            client.get(reverse("madadkar:payment-verify"), {"authority": payment.authority})
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCESS

        resp = client.get(_gateway_url(payment))
        assert resp.status_code == status.HTTP_200_OK
        html = resp.content.decode()
        assert "قبلاً تأیید شده" in html
        # بدون فرم — کلیک مجدد ممکن نیست
        assert "<form" not in html


class TestConfirmCancelFlow:
    """confirm → verify موفق؛ cancel → لغو؛ بدونِ confirm → شکست قطعی."""

    def test_confirm_then_verify_success(self):
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        client, payment, _body = _initiate_unconfirmed(campaign=campaign, user=user)

        confirm = client.post(_gateway_url(payment), data={"action": "confirm"})
        assert confirm.status_code == status.HTTP_302_FOUND
        assert "status=OK" in confirm["Location"]
        assert payment.authority in confirm["Location"]

        with patch(_AUDIT_TASK_PATH):
            verify = client.get(
                reverse("madadkar:payment-verify"),
                {"authority": payment.authority},
            )
        assert verify.status_code == status.HTTP_302_FOUND
        assert "result=success" in verify["Location"]

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCESS
        assert payment.ref_id.startswith("SBXREF-")
        payment.participation.refresh_from_db()
        assert payment.participation.status == ParticipationStatus.PAID

    def test_verify_without_confirm_fails_and_releases_shares(self):
        """کلید باگ: verify مستقیم (بوکمارک/اسکنر/refresh) success ساختگی نمی‌گیرد."""
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        client, payment, _body = _initiate_unconfirmed(campaign=campaign, user=user)

        with patch(_AUDIT_TASK_PATH):
            verify = client.get(
                reverse("madadkar:payment-verify"),
                {"authority": payment.authority},
            )
        assert verify.status_code == status.HTTP_302_FOUND
        assert "result=failed" in verify["Location"]

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        payment.participation.refresh_from_db()
        assert payment.participation.status == ParticipationStatus.FAILED
        campaign.refresh_from_db()
        assert campaign.purchased_shares == 0

    def test_cancel_via_page_releases_reservation(self):
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        client, payment, _body = _initiate_unconfirmed(campaign=campaign, user=user)

        cancel = client.post(_gateway_url(payment), data={"action": "cancel"})
        assert cancel.status_code == status.HTTP_302_FOUND
        assert "status=NOK" in cancel["Location"]

        with patch(_AUDIT_TASK_PATH):
            verify = client.get(
                reverse("madadkar:payment-verify"),
                {"authority": payment.authority, "status": "NOK"},
            )
        assert verify.status_code == status.HTTP_302_FOUND
        assert "result=canceled" in verify["Location"]
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED

    def test_confirm_double_click_is_safe(self):
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        client, payment, _body = _initiate_unconfirmed(campaign=campaign, user=user)

        assert client.post(_gateway_url(payment), data={"action": "confirm"}).status_code == 302
        assert client.post(_gateway_url(payment), data={"action": "confirm"}).status_code == 302

        with patch(_AUDIT_TASK_PATH):
            verify = client.get(
                reverse("madadkar:payment-verify"),
                {"authority": payment.authority},
            )
        assert "result=success" in verify["Location"]

    def test_invalid_action_rerenders_page_without_marker(self):
        campaign = PublishedCampaignFactory(total_amount=10_000_000, total_shares=10)
        user = UserFactory()
        client, payment, _body = _initiate_unconfirmed(campaign=campaign, user=user)

        resp = client.post(_gateway_url(payment), data={"action": "hack"})
        assert resp.status_code == status.HTTP_200_OK
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PENDING
        assert payment.gateway_status != "SANDBOX-CONFIRMED"


class TestProductionProviderGuard:
    """production.py باید با provider=sandbox در boot بترکد (RuntimeError، نه warning)."""

    _BASE_ENV = {
        "PATH": "/usr/bin:/bin",
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "SECRET_KEY": "x" * 64,
        "ALLOWED_HOSTS": "example.com",
        "DATABASE_ENGINE": "sqlite",
        "ALLOW_SQLITE_IN_PRODUCTION": "True",
        "CACHE_BACKEND": "redis",
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    }

    def _run(self, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        env = {**self._BASE_ENV, **extra_env}
        repo = Path(__file__).resolve().parents[3]
        return subprocess.run(
            [sys.executable, "-c", "import config.settings.production; print('BOOT_OK')"],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_sandbox_provider_blocks_production_boot(self):
        proc = self._run({"MADADKAR_PAYMENT_PROVIDER": "sandbox"})
        assert proc.returncode != 0
        assert "MADADKAR_PAYMENT_PROVIDER" in proc.stderr
        assert "BOOT_OK" not in proc.stdout

    def test_real_provider_boots(self):
        proc = self._run(
            {
                "MADADKAR_PAYMENT_PROVIDER": "zarinpal",
                "MADADKAR_ZARINPAL_MERCHANT_ID": "ci-dummy-merchant",
            },
        )
        assert proc.returncode == 0, proc.stderr
        assert "BOOT_OK" in proc.stdout
