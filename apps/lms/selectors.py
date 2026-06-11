"""
Selector layer for LMS read-side queries.

All read queries for public, user, and admin scopes pass through this module so
query optimization and visibility rules stay centralized.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, QuerySet

from apps.lms.models import Course, Enrollment, Lesson, LMSCategory, LMSUserSkill


def get_public_categories() -> QuerySet[LMSCategory]:
    """Return active LMS categories for public navigation."""
    return LMSCategory.objects.active().order_by("order", "title")


def get_public_category_by_slug(slug: str) -> LMSCategory | None:
    """Return one active category by slug."""
    return get_public_categories().filter(slug=slug).first()


def get_admin_categories() -> QuerySet[LMSCategory]:
    """Return all categories for admin management."""
    return LMSCategory.all_objects.annotate(courses_count=Count("courses")).order_by("order", "title")


def get_admin_category_by_id(category_id: int) -> LMSCategory | None:
    """Return one category for admin scope."""
    return LMSCategory.all_objects.filter(pk=category_id).first()


def get_public_courses() -> QuerySet[Course]:
    """Return published courses with category and active lessons prefetched."""
    return (
        Course.objects.published()
        .with_category()
        .prefetch_related(Prefetch("lessons", queryset=Lesson.objects.active().ordered()))
    )


def get_public_course_by_slug(slug: str) -> Course | None:
    """Return one published course by slug or None."""
    return get_public_courses().filter(slug=slug).first()


def get_admin_courses() -> QuerySet[Course]:
    """Return all courses for admin scope."""
    return Course.all_objects.with_category().prefetch_related("lessons").order_by("-created_at")


def get_admin_course_by_id(course_id: int) -> Course | None:
    """Return one course by id for admin scope."""
    return get_admin_courses().filter(pk=course_id).first()


def get_course_lessons(*, course: Course, public_only: bool = True) -> QuerySet[Lesson]:
    """Return lessons for a course in display order."""
    queryset = Lesson.objects if public_only else Lesson.all_objects
    queryset = queryset.filter(course=course)
    if public_only:
        queryset = queryset.active()
    return queryset.ordered()


def get_lesson_by_slug(*, course: Course, lesson_slug: str, public_only: bool = True) -> Lesson | None:
    """Return one lesson by course and slug."""
    return get_course_lessons(course=course, public_only=public_only).filter(slug=lesson_slug).first()


def get_admin_lesson_by_id(*, lesson_id: int) -> Lesson | None:
    """Return one lesson for admin scope."""
    return Lesson.all_objects.select_related("course").filter(pk=lesson_id).first()


def get_user_enrollments(*, user_id: int) -> QuerySet[Enrollment]:
    """Return enrollments owned by a user."""
    return (
        Enrollment.objects.select_related("course", "course__category", "last_accessed_lesson")
        .prefetch_related("lesson_progress__lesson")
        .filter(user_id=user_id)
    )


def get_user_enrollment_by_id(*, user_id: int, enrollment_id: int) -> Enrollment | None:
    """Return one enrollment with IDOR protection."""
    return get_user_enrollments(user_id=user_id).filter(pk=enrollment_id).first()


def get_user_skills(*, user_id: int) -> QuerySet[LMSUserSkill]:
    """Return skills visible on a user's profile."""
    return LMSUserSkill.objects.filter(user_id=user_id).select_related("course", "certificate")


def get_course_report_queryset(*, course_id: int) -> QuerySet[Enrollment]:
    """Return enrollment rows for admin course report."""
    return (
        Enrollment.objects.filter(course_id=course_id)
        .select_related("user", "course", "certificate")
        .order_by("-enrolled_at")
    )


def get_user_enrollment_for_course(*, user_id: int, course_id: int) -> Enrollment | None:
    """Return the user's enrollment for a course, if any."""
    return get_user_enrollments(user_id=user_id).filter(course_id=course_id).first()


def get_lesson_for_progress(*, lesson_id: int) -> Lesson | None:
    """Return an active lesson with course for progress updates."""
    return Lesson.objects.select_related("course").filter(pk=lesson_id, is_active=True).first()


def get_lesson_questions(*, lesson_id: int) -> QuerySet:
    """Return visible/flagged questions for a lesson with visible answers prefetched."""
    from django.db.models import Prefetch

    from apps.lms.choices import DiscussionStatus
    from apps.lms.models import LessonAnswer, LessonQuestion

    return (
        LessonQuestion.objects.filter(
            lesson_id=lesson_id,
            status__in=[DiscussionStatus.VISIBLE, DiscussionStatus.FLAGGED],
        )
        .select_related("user", "lesson", "lesson__course")
        .prefetch_related(
            Prefetch(
                "answers",
                queryset=LessonAnswer.objects.filter(
                    status__in=[DiscussionStatus.VISIBLE, DiscussionStatus.FLAGGED],
                ).select_related("user"),
            )
        )
        .order_by("-is_pinned", "-last_activity_at")
    )


def get_lesson_question_by_id(*, question_id: int):
    """Return a question by id with relations loaded."""
    from apps.lms.models import LessonQuestion

    return (
        LessonQuestion.objects.select_related("user", "lesson", "lesson__course")
        .prefetch_related("answers__user")
        .filter(pk=question_id)
        .first()
    )


def get_lesson_answer_by_id(*, answer_id: int):
    """Return an answer by id with question/lesson relations."""
    from apps.lms.models import LessonAnswer

    return LessonAnswer.objects.select_related("question", "question__lesson", "user").filter(pk=answer_id).first()


def get_admin_discussion_reports() -> QuerySet:
    """Return discussion reports for admin moderation."""
    from apps.lms.models import LessonDiscussionReport

    return LessonDiscussionReport.objects.select_related(
        "reported_by", "reviewed_by", "question", "answer"
    ).order_by("-created_at")


def get_admin_discussion_report_by_id(*, report_id: int):
    """Return one discussion report for admin moderation."""
    return get_admin_discussion_reports().filter(pk=report_id).first()


def get_published_quiz_for_course(*, course: Course):
    """Return published quiz for a course, if any."""
    from apps.lms.choices import QuizStatus
    from apps.lms.models import Quiz

    return (
        Quiz.objects.filter(course=course, status=QuizStatus.PUBLISHED, is_active=True)
        .prefetch_related("questions__options")
        .first()
    )


def get_admin_quiz_by_course_id(*, course_id: int):
    """Return quiz for a course in admin scope."""
    from apps.lms.models import Quiz

    return Quiz.all_objects.filter(course_id=course_id).prefetch_related("questions__options").first()


def get_quiz_attempt_by_id(*, user_id: int, attempt_id: int):
    """Return one quiz attempt owned by user."""
    from apps.lms.models import QuizAttempt

    return (
        QuizAttempt.objects.select_related("quiz", "course", "enrollment")
        .filter(pk=attempt_id, user_id=user_id)
        .first()
    )


def get_admin_quiz_question_by_id(*, question_id: int):
    """Return quiz question for admin scope."""
    from apps.lms.models import QuizQuestion

    return QuizQuestion.all_objects.select_related("quiz", "quiz__course").filter(pk=question_id).first()


def get_user_certificates(*, user_id: int) -> QuerySet:
    """Return certificates owned by a user."""
    from apps.lms.models import Certificate

    return Certificate.objects.select_related("course", "user").filter(user_id=user_id).order_by("-issued_at")


def get_user_certificate_by_id(*, user_id: int, certificate_id: int):
    """Return one certificate with owner protection."""
    return get_user_certificates(user_id=user_id).filter(pk=certificate_id).first()


def get_certificate_by_verification_slug(*, verification_slug: str):
    """Return a certificate by public verification slug."""
    from apps.lms.models import Certificate

    return Certificate.objects.select_related("course", "user").filter(verification_slug=verification_slug).first()


def get_admin_certificate_by_id(*, certificate_id: int):
    """Return one certificate for admin actions."""
    from apps.lms.models import Certificate

    return Certificate.all_objects.select_related("course", "user").filter(pk=certificate_id).first()
