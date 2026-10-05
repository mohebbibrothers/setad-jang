"""
LMS Phase 3 progress tracking tests.

این تست‌ها ثبت پیشرفت ویدئو را مثل یک سایت آموزشی حرفه‌ای validate می‌کنند:
- فقط کاربر ثبت‌نام‌کرده می‌تواند progress ثبت کند.
- watched_seconds monotonic است و با eventهای عقب‌تر کاهش پیدا نمی‌کند.
- last_position_seconds می‌تواند برای rewind جلو/عقب شود.
- درصد جلسه و دوره از source of truth محاسبه می‌شود.
- تکمیل همه جلسات enrollment را completed می‌کند.
- IDOR و audit dispatch پوشش داده می‌شود.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit_logs import actions as audit_actions
from apps.lms.choices import EnrollmentStatus
from apps.lms.models import Enrollment, LessonProgress
from apps.lms.services import sync_course_counters
from tests.factories import UserFactory
from tests.factories.lms import LessonFactory, PublishedCourseFactory

pytestmark = pytest.mark.django_db

_AUDIT_TASK_PATH = "apps.audit_logs.tasks.create_audit_log_task"


def _client_for(user) -> APIClient:
    """Return authenticated APIClient for user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _complete_profile(user) -> None:
    """Fill minimal LMS enrollment profile fields."""
    user.first_name = "Ali"
    user.last_name = "Mohammadi"
    user.save(update_fields=["first_name", "last_name"])
    user.profile.national_code = "0123456789"
    user.profile.save(update_fields=["national_code"])


def _enroll(user, course) -> Enrollment:
    """Create enrollment through API to exercise real route and service."""
    _complete_profile(user)
    response = _client_for(user).post(reverse("lms:course-enroll", kwargs={"slug": course.slug}))
    assert response.status_code == status.HTTP_201_CREATED, response.data
    return Enrollment.objects.get(user=user, course=course)


class TestLMSLessonProgressAPI:
    """Progress update API contract tests."""

    def test_enrolled_user_can_update_progress_and_audit_is_dispatched(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)

        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            response = _client_for(user).post(
                reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
                data={"watched_seconds": 30, "last_position_seconds": 25},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["watched_seconds"] == 30
        assert response.data["data"]["last_position_seconds"] == 25
        assert response.data["data"]["progress_percent"] == "30.00"

        enrollment.refresh_from_db()
        assert enrollment.watched_seconds == 30
        assert enrollment.progress_percent == 30
        assert enrollment.last_accessed_lesson_id == lesson.pk
        assert mock_task.delay.call_args.kwargs["action"] == audit_actions.LMS_PROGRESS_UPDATED

    def test_progress_is_monotonic_but_last_position_can_rewind(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        _enroll(user, course)
        client = _client_for(user)

        client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 80, "last_position_seconds": 80},
            format="json",
        )
        response = client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 20, "last_position_seconds": 10},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        progress = LessonProgress.objects.get(lesson=lesson)
        assert progress.watched_seconds == 80
        assert progress.last_position_seconds == 10

    def test_course_progress_uses_total_course_duration_not_only_started_lessons(self) -> None:
        course = PublishedCourseFactory()
        lesson_a = LessonFactory(course=course, order=1, duration_seconds=100)
        LessonFactory(course=course, order=2, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)

        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson_a.pk}),
            data={"watched_seconds": 100},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        enrollment.refresh_from_db()
        assert enrollment.watched_seconds == 100
        assert enrollment.total_seconds_snapshot == 200
        assert enrollment.progress_percent == 50
        assert enrollment.status == EnrollmentStatus.ACTIVE

    def test_enrollment_completes_when_all_lessons_are_completed(self) -> None:
        course = PublishedCourseFactory()
        lesson_a = LessonFactory(course=course, order=1, duration_seconds=100)
        lesson_b = LessonFactory(course=course, order=2, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)
        client = _client_for(user)

        client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson_a.pk}),
            data={"watched_seconds": 90},
            format="json",
        )
        response = client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson_b.pk}),
            data={"watched_seconds": 90},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        enrollment.refresh_from_db()
        assert enrollment.status == EnrollmentStatus.COMPLETED
        assert enrollment.completed_at is not None
        # قراردادِ اصلاح‌شده: جلسه‌ای که در آستانه‌ی ۹۰٪ «تکمیل» شود در جمعِ
        # کلاس ۱۰۰ حساب می‌شود؛ کلاسِ COMPLETED دیگر روی ۹۰٪ نمی‌ایستد —
        # وضعیت و نوارِ پیشرفت باید همیشه یک قصه بگویند.
        assert enrollment.progress_percent == 100

    def test_completed_zero_duration_lessons_move_the_class_progress_bar(self) -> None:
        """جلسه‌ی متنی/سندیِ بدونِ duration با mark_completed کامل می‌شود و باید
        نوارِ کلاس را هم جلو ببرد؛ فرمولِ قدیمیِ ثانیه‌محور این را ۰٪ نشان می‌داد."""
        course = PublishedCourseFactory()
        video = LessonFactory(course=course, order=1, duration_seconds=100)
        article = LessonFactory(course=course, order=2, duration_seconds=0, content_type="article")
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)
        client = _client_for(user)

        # زنجیره‌ی تماشا: ویدئو (جلسه‌ی اول) باید پیش از مقاله کامل شود.
        client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": video.pk}),
            data={"watched_seconds": 95},
            format="json",
        )
        enrollment.refresh_from_db()
        assert enrollment.progress_percent == 50
        assert enrollment.status == EnrollmentStatus.ACTIVE

        response = client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": article.pk}),
            data={"mark_completed": True},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        enrollment.refresh_from_db()
        assert enrollment.status == EnrollmentStatus.COMPLETED
        assert enrollment.progress_percent == 100

    def test_class_percent_ignores_stale_estimated_duration(self) -> None:
        """اگر برآوردِ مدتِ کلاس (estimated_duration_seconds) با واقعیتِ جلسات
        فاصله بگیرد، درصدِ کاربر باید از خودِ جلسات حساب شود نه آن برآورد."""
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        LessonFactory(course=course, order=2, duration_seconds=100)
        sync_course_counters(course=course)
        # شبیه‌سازیِ رانشِ داده: ادمین بعداً برآورد را دستی خراب کرده است.
        course.estimated_duration_seconds = 99999
        course.save(update_fields=["estimated_duration_seconds"])
        user = UserFactory()
        enrollment = _enroll(user, course)

        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 100},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        enrollment.refresh_from_db()
        # با فرمولِ قدیمی این عدد ۰٫۱ ٪ می‌شد؛ قراردادِ جدید: نصفِ مسیر = ۵۰٪.
        assert enrollment.progress_percent == 50

    def test_user_cannot_update_progress_without_enrollment(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        user = UserFactory()

        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 10},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert LessonProgress.objects.count() == 0

    def test_user_cannot_read_other_user_enrollment_detail(self) -> None:
        course = PublishedCourseFactory()
        owner = UserFactory()
        other = UserFactory()
        enrollment = _enroll(owner, course)

        response = _client_for(other).get(
            reverse("lms:user-enrollment-detail", kwargs={"enrollment_id": enrollment.pk})
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_enrollment_detail_includes_lesson_progress(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        sync_course_counters(course=course)
        user = UserFactory()
        enrollment = _enroll(user, course)
        client = _client_for(user)
        client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 40},
            format="json",
        )

        response = client.get(
            reverse("lms:user-enrollment-detail", kwargs={"enrollment_id": enrollment.pk})
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]["lesson_progress"]) == 1
        assert response.data["data"]["lesson_progress"][0]["watched_seconds"] == 40


class TestLessonSequenceGate:
    """زنجیره‌ی تماشای پشت‌سرهم — درخواستِ مشتری (یافتهٔ راندِ QA):

    جلسه‌ی N فقط وقتی باز است که همه‌ی جلساتِ فعالِ قبلی تکمیل شده باشند؛
    این قاعده روی رسانه، پیشرفت، و مشارکتِ گفتگو (خواندن/نوشتن) اعمال می‌شود.
    معافیت‌ها: جلسه‌ی اول مسیر، جلساتِ is_preview، ادمین/استاف، و ثبت‌نامِ
    تکمیل‌شده (بازتماشای آزاد).
    """

    VIDEO = "https://cdn.example.com/seq.mp4"

    def _two_lesson_course(self):
        course = PublishedCourseFactory()
        first = LessonFactory(course=course, order=1, duration_seconds=100, video_url=self.VIDEO)
        second = LessonFactory(course=course, order=2, duration_seconds=100, video_url=self.VIDEO)
        sync_course_counters(course=course)
        return course, first, second

    def _media(self, user, lesson):
        return _client_for(user).get(
            reverse(
                "lms:lesson-media-access",
                kwargs={"lesson_id": lesson.pk, "media_kind": "video"},
            )
        )

    def _progress(self, user, lesson, watched):
        with patch(_AUDIT_TASK_PATH) as mock_task:
            mock_task.delay = MagicMock()
            return _client_for(user).post(
                reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
                data={"watched_seconds": watched},
                format="json",
            )

    def test_second_lesson_media_locked_until_first_completed(self) -> None:
        course, first, second = self._two_lesson_course()
        user = UserFactory()
        _enroll(user, course)

        blocked = self._media(user, second)
        assert blocked.status_code == status.HTTP_403_FORBIDDEN
        assert first.title in blocked.data["message"] or "قفل" in blocked.data["message"]

        # جلسه‌ی اول مسیر همیشه باز است
        assert self._media(user, first).status_code == status.HTTP_200_OK

        # با کامل‌شدن جلسه‌ی اول، دومی باز می‌شود
        done = self._progress(user, first, 95)
        assert done.status_code == status.HTTP_200_OK
        assert self._media(user, second).status_code == status.HTTP_200_OK

    def test_progress_update_rejected_before_previous_completed(self) -> None:
        course, first, second = self._two_lesson_course()
        user = UserFactory()
        _enroll(user, course)

        blocked = self._progress(user, second, 30)
        assert blocked.status_code == status.HTTP_403_FORBIDDEN
        assert first.title in blocked.data["message"] or "قفل" in blocked.data["message"]
        assert not LessonProgress.objects.filter(lesson=second).exists()

    def test_preview_lesson_is_exempt_from_sequence(self) -> None:
        course, first, _second = self._two_lesson_course()
        preview = LessonFactory(
            course=course, order=3, duration_seconds=100, video_url=self.VIDEO, is_preview=True
        )
        user = UserFactory()
        _enroll(user, course)
        # بدون تماشای اول/دوم، پیش‌نمایش باز است (ویترینِ بازاریابی)
        assert self._media(user, preview).status_code == status.HTTP_200_OK
        # ولی پاسخ به جلسه‌ی قفل، همچنان نیازمندِ زنجیره است
        assert self._progress(user, first, 95).status_code == status.HTTP_200_OK

    def test_staff_user_skips_sequence(self) -> None:
        course, _first, second = self._two_lesson_course()
        staff = UserFactory(is_staff=True)
        _enroll(staff, course)
        assert self._media(user=staff, lesson=second).status_code == status.HTTP_200_OK

    def test_completed_enrollment_can_rewatch_out_of_order(self) -> None:
        course, first, second = self._two_lesson_course()
        user = UserFactory()
        _enroll(user, course)
        assert self._progress(user, first, 95).status_code == status.HTTP_200_OK
        assert self._progress(user, second, 95).status_code == status.HTTP_200_OK
        enrollment = Enrollment.objects.get(user=user, course=course)
        assert enrollment.status == EnrollmentStatus.COMPLETED

        # جلسه‌ی تازه (بعد از پایانِ مسیر اضافه شده) برای فارغ‌التحصیل باز است
        late = LessonFactory(course=course, order=3, duration_seconds=100, video_url=self.VIDEO)
        assert self._media(user, late).status_code == status.HTTP_200_OK

    def test_questions_reads_and_writes_follow_sequence(self) -> None:
        course, first, second = self._two_lesson_course()
        user = UserFactory()
        _enroll(user, course)

        list_url = reverse("lms:lesson-question-list-create", kwargs={"lesson_id": second.pk})
        assert _client_for(user).get(list_url).status_code == status.HTTP_403_FORBIDDEN
        asked = _client_for(user).post(
            list_url,
            data={"title": "سؤال درباره جلسه", "body": "متن سؤال معتبر است"},
            format="json",
        )
        assert asked.status_code == status.HTTP_403_FORBIDDEN

        assert self._progress(user, first, 95).status_code == status.HTTP_200_OK
        assert _client_for(user).get(list_url).status_code == status.HTTP_200_OK
        asked2 = _client_for(user).post(
            list_url,
            data={"title": "سؤال درباره جلسه", "body": "متن سؤال معتبر است"},
            format="json",
        )
        assert asked2.status_code == status.HTTP_201_CREATED

    def test_answer_create_locked_under_locked_lesson(self) -> None:
        from apps.lms.models import LessonQuestion

        course, first, second = self._two_lesson_course()
        asker = UserFactory()
        replier = UserFactory()
        _enroll(asker, course)
        _enroll(replier, course)
        assert self._progress(asker, first, 95).status_code == status.HTTP_200_OK
        question = LessonQuestion.objects.create(
            lesson=second, user=asker, title="عنوان سؤال", body="متن سؤال معتبر"
        )

        blocked = _client_for(replier).post(
            reverse("lms:question-answer-create", kwargs={"question_id": question.pk}),
            data={"body": "پاسخ من به سؤال تو"},
            format="json",
        )
        assert blocked.status_code == status.HTTP_403_FORBIDDEN

        assert self._progress(replier, first, 95).status_code == status.HTTP_200_OK
        allowed = _client_for(replier).post(
            reverse("lms:question-answer-create", kwargs={"question_id": question.pk}),
            data={"body": "پاسخ من به سؤال تو"},
            format="json",
        )
        assert allowed.status_code == status.HTTP_201_CREATED


class TestDocumentEngagementGate:
    """گیتِ «اول سند را باز کن، بعد تأیید تکمیل» — روی سیم، نه فقط UI."""

    def test_document_mark_completed_without_opening_is_400(self) -> None:
        from tests.factories.lms import DocumentLessonFactory

        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)
        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 10, "mark_completed": True},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "باز" in str(response.data)
        # بدون رکوردِ نیمه‌کاره
        assert LessonProgress.objects.filter(lesson=lesson).count() == 0

    def test_media_opened_signal_stamps_and_unlocks_completion(self) -> None:
        from tests.factories.lms import DocumentLessonFactory

        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)
        client = _client_for(user)
        open_resp = client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"media_opened": True},
            format="json",
        )
        assert open_resp.status_code == status.HTTP_200_OK
        progress = LessonProgress.objects.get(lesson=lesson)
        assert progress.media_opened_at is not None
        assert progress.is_completed is False
        done = client.post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 5, "mark_completed": True},
            format="json",
        )
        assert done.status_code == status.HTTP_200_OK
        progress.refresh_from_db()
        assert progress.is_completed is True

    def test_completion_in_same_request_with_open_signal_is_allowed(self) -> None:
        from tests.factories.lms import DocumentLessonFactory

        course = PublishedCourseFactory()
        lesson = DocumentLessonFactory(course=course, order=1)
        user = UserFactory()
        _enroll(user, course)
        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"mark_completed": True, "media_opened": True},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        progress = LessonProgress.objects.get(lesson=lesson)
        assert progress.is_completed is True
        assert progress.media_opened_at is not None

    def test_video_completion_is_unaffected_by_document_gate(self) -> None:
        course = PublishedCourseFactory()
        lesson = LessonFactory(course=course, order=1, duration_seconds=100)
        user = UserFactory()
        _enroll(user, course)
        response = _client_for(user).post(
            reverse("lms:lesson-progress-update", kwargs={"lesson_id": lesson.pk}),
            data={"watched_seconds": 95, "last_position_seconds": 95},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert LessonProgress.objects.get(lesson=lesson).is_completed is True
