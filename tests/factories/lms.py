"""
Factories for the LMS application.

These factories build deterministic LMS domain objects for tests without invoking
service-layer mutations. Tests that verify counters/state transitions should use
services once implemented.
"""

from __future__ import annotations

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.authentication.choices import Gender
from apps.lms.choices import (
    BadgeLevel,
    CertificateStatus,
    CourseLevel,
    CourseStatus,
    EnrollmentStatus,
    QuizAttemptStatus,
    QuizStatus,
)
from apps.lms.models import (
    Certificate,
    Course,
    Enrollment,
    Lesson,
    LessonProgress,
    LMSCategory,
    LMSUserSkill,
    Quiz,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
)
from tests.factories.auth import UserFactory


class LMSCategoryFactory(DjangoModelFactory):
    """Factory for dynamic LMS categories."""

    class Meta:
        model = LMSCategory

    title = factory.Sequence(lambda n: f"دسته آموزش {n}")
    description = "توضیحات دسته آموزشی"
    order = factory.Sequence(lambda n: n)
    is_active = True


class CourseFactory(DjangoModelFactory):
    """Factory for draft LMS courses."""

    class Meta:
        model = Course

    category = factory.SubFactory(LMSCategoryFactory)
    title = factory.Sequence(lambda n: f"دوره آموزشی {n}")
    subtitle = "زیرعنوان دوره"
    short_description = "توضیح کوتاه دوره"
    description = "توضیحات کامل دوره آموزشی"
    instructor_name = "استاد تست"
    instructor_bio = "رزومه استاد تست"
    level = CourseLevel.BEGINNER
    status = CourseStatus.DRAFT
    language = "fa"
    is_active = True


class PublishedCourseFactory(CourseFactory):
    """Factory for public/published LMS courses."""

    status = CourseStatus.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)


class LessonFactory(DjangoModelFactory):
    """Factory for LMS lessons."""

    class Meta:
        model = Lesson

    course = factory.SubFactory(CourseFactory)
    title = factory.Sequence(lambda n: f"جلسه {n}")
    description = "توضیحات جلسه"
    order = factory.Sequence(lambda n: n + 1)
    duration_seconds = 600
    is_active = True


class EnrollmentFactory(DjangoModelFactory):
    """Factory for course enrollments."""

    class Meta:
        model = Enrollment

    course = factory.SubFactory(PublishedCourseFactory)
    user = factory.SubFactory(UserFactory)
    status = EnrollmentStatus.ACTIVE
    enrolled_at = factory.LazyFunction(timezone.now)
    total_seconds_snapshot = 600


class LessonProgressFactory(DjangoModelFactory):
    """Factory for lesson progress records."""

    class Meta:
        model = LessonProgress

    enrollment = factory.SubFactory(EnrollmentFactory)
    lesson = factory.SubFactory(LessonFactory)
    watched_seconds = 0
    duration_seconds_snapshot = 600
    progress_percent = 0


class QuizFactory(DjangoModelFactory):
    """Factory for LMS course quizzes."""

    class Meta:
        model = Quiz

    course = factory.SubFactory(PublishedCourseFactory)
    title = "آزمون پایانی"
    description = "توضیحات آزمون"
    status = QuizStatus.DRAFT
    time_limit_minutes = 30
    passing_score = 12
    max_attempts = 2
    retake_delay_days = 14


class PublishedQuizFactory(QuizFactory):
    """Factory for published quizzes."""

    status = QuizStatus.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)


class QuizQuestionFactory(DjangoModelFactory):
    """Factory for weighted quiz questions."""

    class Meta:
        model = QuizQuestion

    quiz = factory.SubFactory(QuizFactory)
    text = factory.Sequence(lambda n: f"سؤال آزمون {n}")
    explanation = "توضیح پاسخ"
    order = factory.Sequence(lambda n: n + 1)
    weight = 1


class QuizOptionFactory(DjangoModelFactory):
    """Factory for quiz options."""

    class Meta:
        model = QuizOption

    question = factory.SubFactory(QuizQuestionFactory)
    text = factory.Sequence(lambda n: f"گزینه {n}")
    is_correct = False
    order = factory.Sequence(lambda n: n + 1)


class QuizAttemptFactory(DjangoModelFactory):
    """Factory for quiz attempts."""

    class Meta:
        model = QuizAttempt

    quiz = factory.SubFactory(PublishedQuizFactory)
    course = factory.SelfAttribute("quiz.course")
    user = factory.SubFactory(UserFactory)
    enrollment = factory.SubFactory(EnrollmentFactory)
    attempt_number = 1
    status = QuizAttemptStatus.IN_PROGRESS
    started_at = factory.LazyFunction(timezone.now)


class CertificateFactory(DjangoModelFactory):
    """Factory for issued LMS certificates."""

    class Meta:
        model = Certificate

    quiz_attempt = factory.SubFactory(QuizAttemptFactory)
    user = factory.SelfAttribute("quiz_attempt.user")
    course = factory.SelfAttribute("quiz_attempt.course")
    enrollment = factory.SelfAttribute("quiz_attempt.enrollment")
    status = CertificateStatus.ISSUED
    full_name_snapshot = "کاربر تست"
    gender_snapshot = Gender.MALE
    national_code_snapshot = "0012345678"
    course_title_snapshot = factory.SelfAttribute("course.title")
    instructor_name_snapshot = factory.SelfAttribute("course.instructor_name")
    score_out_of_20 = 18


class LMSUserSkillFactory(DjangoModelFactory):
    """Factory for awarded LMS skills/badges."""

    class Meta:
        model = LMSUserSkill

    user = factory.SubFactory(UserFactory)
    course = factory.SubFactory(PublishedCourseFactory)
    certificate = factory.SubFactory(CertificateFactory)
    title = factory.SelfAttribute("course.title")
    badge_level = BadgeLevel.GOLD
    issued_at = factory.LazyFunction(timezone.now)
