"""
Selector layer for LMS read-side queries.

All read queries for public, user, and admin scopes pass through this module so
query optimization and visibility rules stay centralized.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, QuerySet

from apps.lms.choices import CourseLevel, EnrollmentStatus
from apps.lms.models import (
    Course,
    Enrollment,
    LearningActivityStatement,
    Lesson,
    LMSCategory,
    LMSUserSkill,
)


def get_public_categories() -> QuerySet[LMSCategory]:
    """Return active LMS categories for public navigation."""
    return LMSCategory.objects.active().order_by("order", "title")


def get_public_category_by_slug(slug: str) -> LMSCategory | None:
    """Return one active category by slug."""
    return get_public_categories().filter(slug=slug).first()


def get_admin_categories() -> QuerySet[LMSCategory]:
    """Return all categories for admin management."""
    return LMSCategory.all_objects.annotate(courses_count=Count("courses")).order_by(
        "order", "title"
    )


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


def get_lesson_by_slug(
    *, course: Course, lesson_slug: str, public_only: bool = True
) -> Lesson | None:
    """Return one lesson by course and slug."""
    return (
        get_course_lessons(course=course, public_only=public_only).filter(slug=lesson_slug).first()
    )


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

    return (
        LessonAnswer.objects.select_related("question", "question__lesson", "user")
        .filter(pk=answer_id)
        .first()
    )


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

    return (
        Quiz.all_objects.filter(course_id=course_id).prefetch_related("questions__options").first()
    )


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

    return (
        QuizQuestion.all_objects.select_related("quiz", "quiz__course")
        .filter(pk=question_id)
        .first()
    )


def get_user_certificates(*, user_id: int) -> QuerySet:
    """Return certificates owned by a user."""
    from apps.lms.models import Certificate

    return (
        Certificate.objects.select_related("course", "user")
        .filter(user_id=user_id)
        .order_by("-issued_at")
    )


def get_user_certificate_by_id(*, user_id: int, certificate_id: int):
    """Return one certificate with owner protection."""
    return get_user_certificates(user_id=user_id).filter(pk=certificate_id).first()


def get_certificate_by_verification_slug(*, verification_slug: str):
    """Return a certificate by public verification slug."""
    from apps.lms.models import Certificate

    return (
        Certificate.objects.select_related("course", "user")
        .filter(verification_slug=verification_slug)
        .first()
    )


def get_admin_certificate_by_id(*, certificate_id: int):
    """Return one certificate for admin actions."""
    from apps.lms.models import Certificate

    return (
        Certificate.all_objects.select_related("course", "user").filter(pk=certificate_id).first()
    )


def get_course_analytics(*, course: Course) -> dict:
    """Return admin analytics summary for a course."""
    from django.db.models import Avg

    from apps.lms.choices import EnrollmentStatus, QuizAttemptStatus
    from apps.lms.models import Certificate, QuizAttempt

    enrollments = Enrollment.objects.filter(course=course)
    attempts = QuizAttempt.objects.filter(course=course)
    avg_score = attempts.exclude(submitted_at__isnull=True).aggregate(avg=Avg("score_out_of_20"))[
        "avg"
    ]
    return {
        "participants_count": enrollments.count(),
        "active_count": enrollments.filter(status=EnrollmentStatus.ACTIVE).count(),
        "completed_count": enrollments.filter(status=EnrollmentStatus.COMPLETED).count(),
        "graduates_count": Certificate.objects.filter(course=course, is_active=True).count(),
        "average_progress_percent": float(
            enrollments.aggregate(avg=Avg("progress_percent"))["avg"] or 0
        ),
        "quiz_attempts_count": attempts.count(),
        "quiz_passed_count": attempts.filter(status=QuizAttemptStatus.PASSED).count(),
        "quiz_failed_count": attempts.filter(status=QuizAttemptStatus.FAILED).count(),
        "average_score_out_of_20": float(avg_score) if avg_score is not None else None,
    }


def get_course_leaderboard(*, course: Course) -> list[dict]:
    """Return top learners for a course by score, certificate, and progress."""
    from django.db.models import Max

    enrollments = (
        Enrollment.objects.filter(course=course)
        .select_related("user", "certificate", "certificate__skill")
        .annotate(best_score=Max("quiz_attempts__score_out_of_20"))
        .order_by("-best_score", "-progress_percent", "user_id")
    )
    rows: list[dict] = []
    for enrollment in enrollments:
        certificate = getattr(enrollment, "certificate", None)
        skill = getattr(certificate, "skill", None) if certificate else None
        rows.append(
            {
                "user_id": enrollment.user_id,
                "full_name": getattr(enrollment.user, "full_name", "") or str(enrollment.user),
                "email": getattr(enrollment.user, "email", "") or "",
                "progress_percent": float(enrollment.progress_percent or 0),
                "best_score_out_of_20": float(enrollment.best_score)
                if enrollment.best_score is not None
                else None,
                "badge_level": getattr(skill, "badge_level", "") if skill else "",
                "certificate_code": getattr(certificate, "certificate_code", "")
                if certificate
                else "",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Learning recommendations — user scope
# ---------------------------------------------------------------------------

_LEVEL_ORDER = {
    CourseLevel.BEGINNER: 1,
    CourseLevel.INTERMEDIATE: 2,
    CourseLevel.ADVANCED: 3,
    CourseLevel.PROFESSIONAL: 4,
}


def get_user_learning_recommendations(*, user_id: int, limit: int = 10) -> list[dict]:
    """Return deterministic course recommendations for one learner.

    Ranking signals:
    - exclude already enrolled courses
    - category affinity from existing enrollments and earned skills
    - level progression toward the next difficulty
    - skill-gap coverage for categories without a completed skill
    - course popularity/featured boosts
    """
    safe_limit = max(1, min(limit, 50))
    enrollments = list(
        Enrollment.objects.filter(user_id=user_id)
        .select_related("course", "course__category")
        .order_by("-enrolled_at")
    )
    enrolled_course_ids = {enrollment.course_id for enrollment in enrollments}
    category_affinity = _build_lms_category_affinity(enrollments=enrollments, user_id=user_id)
    completed_category_ids = set(
        LMSUserSkill.objects.filter(user_id=user_id).values_list("course__category_id", flat=True)
    )
    preferred_next_level = _preferred_next_course_level(enrollments=enrollments)
    candidates = Course.objects.published().with_category().exclude(pk__in=enrolled_course_ids)
    scored = [
        _score_recommended_course(
            course=course,
            category_affinity=category_affinity,
            completed_category_ids=completed_category_ids,
            preferred_next_level=preferred_next_level,
        )
        for course in candidates
    ]
    scored = [item for item in scored if item["score"] > 0]
    scored.sort(
        key=lambda item: (-item["score"], -item["course"].enrollments_count, item["course"].title)
    )
    return scored[:safe_limit]


def get_admin_learning_recommendation_overview(*, limit: int = 10) -> dict:
    """Return admin overview of recommendation-ready courses and cold-start gaps."""
    safe_limit = max(1, min(limit, 50))
    published = Course.objects.published().with_category().order_by("-enrollments_count", "title")
    cold_start = published.filter(enrollments_count=0).count()
    featured = published.filter(is_featured=True).count()
    return {
        "published_courses": published.count(),
        "featured_courses": featured,
        "cold_start_courses": cold_start,
        "top_recommendable_courses": [
            {
                "course_id": course.pk,
                "title": course.title,
                "category_title": course.category.title,
                "level": course.level,
                "enrollments_count": course.enrollments_count,
                "is_featured": course.is_featured,
            }
            for course in published[:safe_limit]
        ],
    }


def _build_lms_category_affinity(*, enrollments: list[Enrollment], user_id: int) -> dict[int, int]:
    """Build category affinity from enrollment progress and awarded skills."""
    affinity: dict[int, int] = {}
    for enrollment in enrollments:
        category_id = enrollment.course.category_id
        affinity[category_id] = affinity.get(category_id, 0) + 20
        if enrollment.status == EnrollmentStatus.COMPLETED:
            affinity[category_id] += 20
        if enrollment.progress_percent >= 50:
            affinity[category_id] += 10
    for category_id in LMSUserSkill.objects.filter(user_id=user_id).values_list(
        "course__category_id", flat=True
    ):
        affinity[category_id] = affinity.get(category_id, 0) + 25
    return affinity


def _preferred_next_course_level(*, enrollments: list[Enrollment]) -> str | None:
    """Infer next recommended course level from learner history."""
    if not enrollments:
        return CourseLevel.BEGINNER
    max_level_value = max(
        _LEVEL_ORDER.get(enrollment.course.level, 1) for enrollment in enrollments
    )
    for level, order in _LEVEL_ORDER.items():
        if order == min(max_level_value + 1, max(_LEVEL_ORDER.values())):
            return level
    return CourseLevel.PROFESSIONAL


def _score_recommended_course(
    *,
    course: Course,
    category_affinity: dict[int, int],
    completed_category_ids: set[int],
    preferred_next_level: str | None,
) -> dict:
    """Score one course recommendation and attach reason codes."""
    score = 10
    reason_codes = ["published_course"]
    affinity_score = category_affinity.get(course.category_id, 0)
    if affinity_score:
        score += affinity_score
        reason_codes.append("category_affinity")
    if course.category_id not in completed_category_ids:
        score += 15
        reason_codes.append("skill_gap_category")
    if preferred_next_level and course.level == preferred_next_level:
        score += 18
        reason_codes.append("level_progression")
    if course.is_featured:
        score += 8
        reason_codes.append("featured_course")
    if course.enrollments_count:
        score += min(course.enrollments_count, 20)
        reason_codes.append("popular_course")
    return {
        "course": course,
        "score": score,
        "reason_codes": reason_codes,
    }


# ---------------------------------------------------------------------------
# Learning activity statements — admin scope
# ---------------------------------------------------------------------------


def get_admin_learning_activity_statements() -> QuerySet[LearningActivityStatement]:
    """Return xAPI-like LMS learning statements for admin analytics/export."""
    return LearningActivityStatement.objects.select_related(
        "actor", "course", "lesson", "enrollment", "quiz_attempt", "certificate"
    ).order_by("-occurred_at", "-created_at")
