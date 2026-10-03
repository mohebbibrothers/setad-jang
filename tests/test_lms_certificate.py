"""
LMS Phase 6 certificate and skill/badge tests.

این تست‌ها تضمین می‌کنند پس از قبولی در آزمون، مدرک قابل اعتبارسنجی عمومی، PDF
اولیه، مهارت/مدال پروفایل و revoke ادمین درست کار می‌کنند.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.authentication.choices import Gender
from apps.lms.certificate import build_certificate_text, honorific_for_gender
from apps.lms.choices import BadgeLevel, CertificateStatus
from apps.lms.models import (
    Certificate,
    Enrollment,
    LessonProgress,
    LMSUserSkill,
    QuizOption,
    QuizQuestion,
)
from apps.lms.services import publish_quiz, sync_course_counters
from tests.factories import AdminUserFactory, UserFactory
from tests.factories.lms import LessonFactory, PublishedCourseFactory, QuizFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Return authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _complete_profile(user, *, gender: str = Gender.MALE) -> None:
    """Fill user profile for enrollment/certificate snapshots."""
    user.first_name = "علی"
    user.last_name = "محمدی"
    user.save(update_fields=["first_name", "last_name"])
    user.profile.national_code = "0250915308"
    user.profile.gender = gender
    user.profile.save(update_fields=["national_code", "gender"])


def _build_quiz(course):
    """Build a simple published quiz with one correct answer."""
    quiz = QuizFactory(course=course, passing_score=Decimal("12.00"))
    question = QuizQuestion.objects.create(
        quiz=quiz, text="پایتون چیست؟", order=1, weight=Decimal("1.00")
    )
    wrong = QuizOption.objects.create(
        question=question, text="یک مرورگر", order=1, is_correct=False
    )
    correct = QuizOption.objects.create(
        question=question, text="یک زبان برنامه‌نویسی", order=2, is_correct=True
    )
    publish_quiz(quiz=quiz)
    return quiz, question, correct, wrong


def _pass_quiz_and_return_certificate(*, user, course) -> Certificate:
    """Enroll user, pass quiz via API, and return issued certificate."""
    _complete_profile(user, gender=Gender.FEMALE)
    client = _client_for(user)
    enroll_response = client.post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
    assert enroll_response.status_code == status.HTTP_201_CREATED
    # دروازه‌ی آمادگی: همه‌ی جلساتِ فعال باید پیش از آغاز آزمون تکمیل شده باشند
    enrollment = Enrollment.objects.get(user=user, course=course)
    for lesson in course.lessons.filter(is_active=True):
        LessonProgress.objects.create(enrollment=enrollment, lesson=lesson, is_completed=True)
    _quiz, question, correct, _wrong = _build_quiz(course)
    start_response = client.post(reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug}))
    assert start_response.status_code == status.HTTP_201_CREATED
    attempt_id = start_response.data["data"]["id"]
    submit_response = client.post(
        reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": attempt_id}),
        data={"answers": [{"question_id": question.pk, "selected_option_id": correct.pk}]},
        format="json",
    )
    assert submit_response.status_code == status.HTTP_200_OK
    return Certificate.objects.get(user=user, course=course)


class TestLMSCertificateIssuance:
    """Certificate issuance after passing quiz."""

    def test_passed_quiz_issues_certificate_pdf_and_skill_badge(self) -> None:
        course = PublishedCourseFactory(title="آموزش پایتون", instructor_name="استاد پایتون")
        LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory(email="cert-user@example.com")

        certificate = _pass_quiz_and_return_certificate(user=user, course=course)

        assert certificate.status == CertificateStatus.ISSUED
        assert certificate.full_name_snapshot == "علی محمدی"
        assert certificate.gender_snapshot == Gender.FEMALE
        assert certificate.national_code_snapshot == "0250915308"
        assert certificate.course_title_snapshot == "آموزش پایتون"
        assert certificate.pdf_file.name.endswith(".pdf")
        assert certificate.pdf_file.size > 0
        skill = LMSUserSkill.objects.get(user=user, course=course)
        assert skill.certificate_id == certificate.pk
        assert skill.badge_level == BadgeLevel.DISTINCTION

    def test_certificate_text_uses_gender_honorific_and_basat_mardom_name(self) -> None:
        course = PublishedCourseFactory(title="آموزش Django")
        user = UserFactory(email="cert-text@example.com")
        certificate = _pass_quiz_and_return_certificate(user=user, course=course)

        text = build_certificate_text(certificate)

        assert honorific_for_gender(Gender.FEMALE) == "خانم"
        assert "خانم علی محمدی" in text
        assert "سامانه بعثت مردم" in text
        assert "0250915308" in text

    def test_certificate_issue_is_idempotent_for_same_passed_attempt(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory(email="cert-idempotent@example.com")
        certificate = _pass_quiz_and_return_certificate(user=user, course=course)
        count_before = Certificate.objects.count()

        from apps.lms.services import issue_certificate_for_attempt

        returned = issue_certificate_for_attempt(attempt=certificate.quiz_attempt)

        assert returned.pk == certificate.pk
        assert Certificate.objects.count() == count_before
        assert LMSUserSkill.objects.filter(user=user, course=course).count() == 1


class TestLMSCertificateAPIs:
    """Certificate verification, user list/detail, and admin revoke APIs."""

    def test_public_certificate_verification_endpoint(self) -> None:
        course = PublishedCourseFactory(title="آموزش CSS")
        user = UserFactory(email="verify-cert@example.com")
        certificate = _pass_quiz_and_return_certificate(user=user, course=course)

        response = APIClient().get(
            reverse(
                "lms:certificate-verify",
                kwargs={"verification_slug": certificate.verification_slug},
            )
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["certificate_code"] == certificate.certificate_code
        assert response.data["data"]["status"] == CertificateStatus.ISSUED
        assert "سامانه بعثت مردم" in response.data["data"]["statement"]

    def test_user_certificate_list_and_detail_are_owner_scoped(self) -> None:
        course = PublishedCourseFactory()
        owner = UserFactory(email="owner-cert@example.com")
        other = UserFactory(email="other-cert@example.com")
        certificate = _pass_quiz_and_return_certificate(user=owner, course=course)

        list_response = _client_for(owner).get(reverse("lms:user-certificate-list"))
        other_detail = _client_for(other).get(
            reverse("lms:user-certificate-detail", kwargs={"certificate_id": certificate.pk})
        )

        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["data"]["count"] == 1
        assert other_detail.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_can_revoke_certificate_and_skill_is_hidden(self) -> None:
        admin = AdminUserFactory(email="cert-admin@example.com")
        course = PublishedCourseFactory()
        user = UserFactory(email="revoke-cert@example.com")
        certificate = _pass_quiz_and_return_certificate(user=user, course=course)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(admin).post(
                reverse("lms:admin-certificate-revoke", kwargs={"certificate_id": certificate.pk}),
                data={"reason": "صدور اشتباه در آزمون آزمایشی"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        certificate.refresh_from_db()
        assert certificate.status == CertificateStatus.REVOKED
        assert certificate.revoked_by_id == admin.pk
        assert certificate.skill.is_active is False
        verify_response = APIClient().get(
            reverse(
                "lms:certificate-verify",
                kwargs={"verification_slug": certificate.verification_slug},
            )
        )
        assert verify_response.status_code == status.HTTP_404_NOT_FOUND
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_CERTIFICATE_REVOKED


class TestCertificatePdfResilience:
    """Regression: certificate PDF build must never crash the quiz submit flow.

    ریشه‌ی باگِ «خطا در ارسال به سرور» هنگام قبولی: ساختِ PDF مدرک داخل
    تراکنشِ submit می‌ترکید (فونتِ DejaVu در کانتینرِ پروداکشن غایب بود).
    این تست‌ها تضمین می‌کنند ساختِ PDF هرگز فلویِ ارسال را نمی‌شکند.
    """

    def test_font_loader_falls_back_to_default_when_files_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pathlib import Path

        from apps.lms import certificate as cert_module

        monkeypatch.setattr(
            cert_module, "_FONT_CANDIDATES_REGULAR", [Path("/no/such/regular-font.ttf")]
        )
        monkeypatch.setattr(cert_module, "_FONT_CANDIDATES_BOLD", [Path("/no/such/bold-font.ttf")])

        regular = cert_module._font(20)
        bold = cert_module._font(20, bold=True)

        assert regular is not None
        assert bold is not None

    def test_pdf_bytes_are_built_with_bundled_vazirmatn(self) -> None:
        course = PublishedCourseFactory()
        user = UserFactory(email="cert-pdf-bytes@example.com")
        certificate = _pass_quiz_and_return_certificate(user=user, course=course)

        from apps.lms.certificate import build_certificate_pdf_bytes

        pdf_bytes = build_certificate_pdf_bytes(certificate)

        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 10_000

    def test_ensure_certificate_pdf_ready_never_raises_on_build_failure(self) -> None:
        from apps.lms.services import ensure_certificate_pdf_ready

        course = PublishedCourseFactory()
        user = UserFactory(email="cert-resilient@example.com")
        certificate = _pass_quiz_and_return_certificate(user=user, course=course)
        # PDF قبلاً ساخته شده؛ آن را خالی می‌کنیم تا شاخه‌ی بازسازیِ خطادار اجرا شود
        certificate.pdf_file.delete(save=True)

        with (
            patch(
                "apps.lms.certificate.build_certificate_pdf_bytes",
                side_effect=RuntimeError("font boom"),
            ),
            patch("apps.lms.services.logger") as mock_logger,
        ):
            ready = ensure_certificate_pdf_ready(certificate=certificate)

        assert ready is False
        certificate.refresh_from_db()
        assert not certificate.pdf_file
        mock_logger.exception.assert_called_once()
        assert mock_logger.exception.call_args.args[0] == "certificate.pdf_build_failed"

    def test_passed_submit_returns_200_and_attachs_pdf(self) -> None:
        """فلویِ کاملِ قبولی: وضعیت ۲۰۰ + فایلِ PDFِ واقعی — باگِ ۵۰۰ِ قبولی."""
        course = PublishedCourseFactory(title="آزمون قبولی بدون خطا")
        LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory(email="cert-200@example.com")

        certificate = _pass_quiz_and_return_certificate(user=user, course=course)

        certificate.refresh_from_db()
        assert certificate.status == CertificateStatus.ISSUED
        with certificate.pdf_file.open("rb") as pdf_handle:
            assert pdf_handle.read(4) == b"%PDF"
