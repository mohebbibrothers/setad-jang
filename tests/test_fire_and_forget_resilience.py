"""
تست‌های تاب‌آوری dispatchهای fire-and-forget در مسیر request.

ریشهٔ باگ آزمون ۱۴۰۵/۷: ``log_action_async`` و dispatch نوتیفیکیشن داخل
``transaction.on_commit`` مستقیم ``.delay()`` می‌کردند؛ با broker خاموش
(Redis down — همان چیزی که در محیط محلی با runserver بدون docker رایج است)
kombu OperationalError به view نشت می‌کرد و:
- شروع آزمون ۵۰۰ می‌شد، و
- submitِ «همهٔ گزینه‌های صحیح» (تنها مسیری که گواهی + notification دارد)
  ۵۰۰ می‌شد، در حالی که attempt قبلاً PASSED commit شده بود — retry کاربر
  به «قابل ثبت نیست» می‌خورد و flow قفل می‌شد.

اصلاح: هر dispatch اختیاری یا try/catch با fallback امن است. این تست‌ها با
شبیه‌سازی broker-down همان سناریو را قفل می‌کنند.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from kombu.exceptions import OperationalError

pytestmark = pytest.mark.django_db


def _broker_down():
    """delay() را طوری patch می‌کند که دقیقاً خطای Redis-down را بدهد."""
    from unittest.mock import MagicMock

    m = MagicMock(side_effect=OperationalError("Error 111 connecting to 127.0.0.1:6379."))
    return m


class TestAuditFallback:
    """log_action_async: broker down → نوشتن sync، بدون exception."""

    def test_falls_back_to_sync_write(self, monkeypatch):
        import apps.audit_logs.tasks as tasks
        from apps.audit_logs import actions as audit_actions
        from apps.audit_logs.models import AuditLog
        from apps.audit_logs.services import log_action_async

        monkeypatch.setattr(
            tasks.create_audit_log_task,
            "delay",
            _broker_down(),
        )

        log_action_async(
            action=audit_actions.MADADKAR_PAYMENT_FAILED,
            resource_type="unit-test",
            resource_id="fallback-1",
            extra_data={"k": "v"},
        )

        row = AuditLog.objects.filter(resource_id="fallback-1").first()
        assert row is not None, "fallback sync باید رکورد audit را بنویسد"
        assert row.action == audit_actions.MADADKAR_PAYMENT_FAILED
        assert row.extra_data == {"k": "v"}

    def test_never_raises_even_if_sync_write_fails(self, monkeypatch):
        """حتی خرابی کامل audit نباید request کاربر را ۵۰۰ کند."""
        import apps.audit_logs.tasks as tasks
        from apps.audit_logs import services as audit_services

        monkeypatch.setattr(tasks.create_audit_log_task, "delay", _broker_down())

        def _boom(**kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(audit_services, "create_audit_log", _boom)

        audit_services.log_action_async(action="X", resource_type="Y")  # نباید raise کند

    def test_normal_path_still_dispatches_async(self, monkeypatch):
        """مسیر عادی عوض نشده: broker سالم → تسک queue می‌شود، نه sync write."""
        import apps.audit_logs.tasks as tasks
        from apps.audit_logs.models import AuditLog
        from apps.audit_logs.services import log_action_async

        calls = []
        monkeypatch.setattr(
            tasks.create_audit_log_task,
            "delay",
            lambda **kwargs: calls.append(kwargs),
        )

        log_action_async(action="OK", resource_type="Y", resource_id="async-1")

        assert len(calls) == 1
        assert calls[0]["action"] == "OK"
        assert calls[0]["resource_id"] == "async-1"
        assert not AuditLog.objects.filter(resource_id="async-1").exists()


class TestNotificationDispatchFallback:
    """emit_domain_notification: خطای delay در on_commit باید خورده شود."""

    def test_broker_failure_does_not_raise_and_dispatches_inline(
        self, monkeypatch, settings, django_capture_on_commit_callbacks
    ):
        from apps.notifications import domain as notif_domain
        from apps.notifications.choices import NotificationEventStatus
        from apps.notifications.models import NotificationEvent
        from tests.factories import UserFactory

        settings.NOTIFICATIONS_ASYNC_DISPATCH = True

        recipient = UserFactory()

        import apps.notifications.tasks as tasks

        monkeypatch.setattr(tasks.dispatch_notification_event_task, "delay", _broker_down())

        # dispatch_event هم inline صدا زده می‌شود — آن را spy می‌کنیم تا
        # رفتار fallback را بدون ارسال واقعی کانال‌ها بسنجیم.
        inline_calls: list[int] = []

        def _fake_inline(*, event):
            inline_calls.append(event.pk)

        monkeypatch.setattr(notif_domain, "dispatch_event", _fake_inline)

        with django_capture_on_commit_callbacks(execute=True):
            event = notif_domain.emit_domain_notification(
                event_type="unit.broker_down",
                recipient=recipient,
                payload={"title": "t", "body": "b"},
            )
        # callback داخل context اجرا شد و هیچ exception‌ای نشت نکرد
        assert event.status == NotificationEventStatus.PENDING  # spy وضعیت را عوض نمی‌کند

        assert inline_calls == [event.pk], (
            "fallback باید dispatch هم‌زمان را صدا بزند — بدون exception به caller"
        )
        assert NotificationEvent.objects.filter(pk=event.pk).exists()

    def test_inline_dispatch_error_is_swallowed(
        self, monkeypatch, settings, django_capture_on_commit_callbacks
    ):
        """اگر هم broker و هم dispatch هم‌زمان خراب باشند: فقط لاگ، بدون ۵۰۰."""
        from apps.notifications import domain as notif_domain
        from tests.factories import UserFactory

        settings.NOTIFICATIONS_ASYNC_DISPATCH = True
        recipient = UserFactory()

        import apps.notifications.tasks as tasks

        monkeypatch.setattr(tasks.dispatch_notification_event_task, "delay", _broker_down())

        def _boom(*, event):
            raise RuntimeError("SMTP exploded")

        monkeypatch.setattr(notif_domain, "dispatch_event", _boom)

        with django_capture_on_commit_callbacks(execute=True):
            event = notif_domain.emit_domain_notification(
                event_type="unit.both_down",
                recipient=recipient,
                payload={"title": "t", "body": "b"},
            )
        assert event.pk  # event persist شده؛ caller هیچ خطایی نمی‌گیرد


class TestQuizFlowSurvivesBrokerDown:
    """رگرسیونِ دقیقِ باگ کاربری: start/submit آزمون با broker خاموش.

    این تست همان traceback واقعی (log_action_async در views_quiz) را با
    شبیه‌سازی OperationalError ایجاد می‌کند — نه mock در سطح service؛ اگر
    روزی dispatchِ دیگری بدون guard به مسیر view اضافه شود، این تست همان
    طبقه باگ را می‌گیرد.
    """

    @staticmethod
    def _build_published_quiz(ac, course, admin):
        q_res = ac.post(
            reverse("lms:admin-quiz-detail-create", kwargs={"course_id": course.pk}),
            data={"title": "آزمون نهایی", "passing_score": "10.00", "time_limit_minutes": 20},
            format="json",
        )
        assert q_res.status_code in (200, 201), q_res.data
        question_ids = []
        for i in (1, 2):
            qr = ac.post(
                reverse("lms:admin-quiz-question-create", kwargs={"course_id": course.pk}),
                data={"text": f"سؤال {i}", "order": i, "weight": "5.00"},
                format="json",
            )
            assert qr.status_code in (200, 201), qr.data
            qid = qr.data["data"]["id"] if "data" in qr.data else qr.data["id"]
            question_ids.append(qid)
            for oi in range(1, 4):
                or_res = ac.post(
                    reverse("lms:admin-quiz-option-create", kwargs={"question_id": qid}),
                    data={"text": f"گزینه {oi}", "is_correct": oi == 1, "order": oi},
                    format="json",
                )
                assert or_res.status_code in (200, 201), or_res.data
        pub = ac.post(reverse("lms:admin-quiz-publish", kwargs={"course_id": course.pk}))
        assert pub.status_code == 200, pub.data
        return question_ids

    def test_start_and_all_correct_submit_survive_broker_down(
        self,
        monkeypatch,
        settings,
    ):
        from django.urls import reverse
        from rest_framework.test import APIClient

        import apps.audit_logs.tasks as audit_tasks
        import apps.notifications.tasks as notif_tasks
        from apps.lms.models import Enrollment, QuizOption
        from apps.lms.services import update_lesson_progress
        from tests.factories import AdminUserFactory, UserFactory
        from tests.factories.lms import LessonFactory, PublishedCourseFactory

        settings.CELERY_TASK_ALWAYS_EAGER = False  # dispatch واقعی مسیر شود تا patch اثر کند

        admin = AdminUserFactory()
        course = PublishedCourseFactory()
        LessonFactory(course=course, duration_seconds=300)
        ac = APIClient()
        ac.force_authenticate(user=admin)
        self._build_published_quiz(ac, course, admin)

        user = UserFactory()
        user.first_name, user.last_name = "مریم", "رضایی"
        user.save()
        user.profile.national_code = "0066655544"
        user.profile.save()
        lc = APIClient()
        lc.force_authenticate(user=user)
        assert (
            lc.post(reverse("lms:course-enroll", kwargs={"slug": course.slug})).status_code == 201
        )
        enr = Enrollment.objects.get(user=user, course=course)
        for lesson in course.lessons.filter(is_active=True):
            update_lesson_progress(
                enrollment=enr,
                lesson=lesson,
                watched_seconds=lesson.duration_seconds,
                last_position_seconds=lesson.duration_seconds,
                mark_completed=lesson.supports_manual_completion,
            )

        # broker از همین‌جا پایین است — کل viewها باید زنده بمانند
        monkeypatch.setattr(audit_tasks.create_audit_log_task, "delay", _broker_down())
        monkeypatch.setattr(notif_tasks.dispatch_notification_event_task, "delay", _broker_down())

        start = lc.post(reverse("lms:quiz-attempt-start", kwargs={"slug": course.slug}))
        assert start.status_code in (200, 201), start.data
        data = start.data["data"]

        answers = []
        for q in data["questions"]:
            oid = QuizOption.objects.filter(question=q["id"], is_correct=True).first().pk
            answers.append({"question_id": q["id"], "selected_option_id": oid})
        submit = lc.post(
            reverse("lms:quiz-attempt-submit", kwargs={"attempt_id": data["id"]}),
            {"answers": answers},
            format="json",
        )
        assert submit.status_code == 200, submit.data
        assert submit.data["data"]["is_passed"] is True

        from apps.lms.models import QuizAttempt

        attempt = QuizAttempt.objects.get(pk=data["id"])
        assert attempt.is_passed is True

        # auditها هم گم نشده‌اند — fallback sync نوشته
        from apps.audit_logs.models import AuditLog

        assert AuditLog.objects.filter(
            action="LMS_QUIZ_ATTEMPT_SUBMITTED",
            resource_id=str(data["id"]),
        ).exists()
        assert AuditLog.objects.filter(
            action="LMS_QUIZ_ATTEMPT_PASSED",
            resource_id=str(data["id"]),
        ).exists()
