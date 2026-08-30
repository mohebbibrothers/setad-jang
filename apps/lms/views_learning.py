"""گروه دامنه‌ای `views_learning` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, ErrorResponse, SuccessResponse
from apps.lms import selectors, services
from apps.lms.permissions import IsLMSAdminUser
from apps.lms.serializers import (
    EnrollmentDetailSerializer,
    EnrollmentSerializer,
    LearningActivityStatementSerializer,
    LearningRecommendationItemSerializer,
    LearningRecommendationOverviewSerializer,
    LessonMediaAccessSerializer,
    LessonProgressSerializer,
    LessonProgressUpdateSerializer,
    LMSUserSkillSerializer,
)
from apps.lms.services import (
    CourseNotEnrollabeError,
    EnrollmentNotActiveError,
    LessonMediaAccessError,
    LessonMediaUnavailableError,
    LessonNotInEnrollmentCourseError,
    LMSProfileIncompleteError,
)
from apps.lms.throttles import (
    LMSEnrollThrottle,
    LMSProgressThrottle,
)

from .views_common import (  # noqa: F401 — re-exportِ رایگان برای بدنه‌های منتقل‌شده
    ANSWER_RESPONSE,
    CATEGORY_LIST_RESPONSE,
    CATEGORY_RESPONSE,
    CERTIFICATE_LIST_RESPONSE,
    CERTIFICATE_RESPONSE,
    CERTIFICATE_VERIFY_RESPONSE,
    COURSE_ANALYTICS_RESPONSE,
    COURSE_LEADERBOARD_RESPONSE,
    COURSE_LIST_RESPONSE,
    COURSE_REPORT_RESPONSE,
    COURSE_RESPONSE,
    DISCUSSION_REPORT_LIST_RESPONSE,
    DISCUSSION_REPORT_RESPONSE,
    ENROLLMENT_DETAIL_RESPONSE,
    ENROLLMENT_LIST_RESPONSE,
    ENROLLMENT_RESPONSE,
    LEARNING_RECOMMENDATION_OVERVIEW_RESPONSE,
    LEARNING_RECOMMENDATION_RESPONSE,
    LEARNING_STATEMENT_LIST_RESPONSE,
    LESSON_LIST_RESPONSE,
    LESSON_MEDIA_RESPONSE,
    LESSON_PROGRESS_RESPONSE,
    LESSON_RESPONSE,
    LMS_ERROR_RESPONSE,
    QUESTION_LIST_RESPONSE,
    QUESTION_RESPONSE,
    QUIZ_ADMIN_RESPONSE,
    QUIZ_ATTEMPT_RESPONSE,
    QUIZ_OPTION_RESPONSE,
    QUIZ_PUBLIC_RESPONSE,
    QUIZ_QUESTION_RESPONSE,
    QUIZ_UNLOCK_RESPONSE,
    SKILL_LIST_RESPONSE,
    TAG_LMS_ADMIN,
    TAG_LMS_PUBLIC,
    TAG_LMS_USER,
    VIDEO_PROCESSING_JOB_RESPONSE,
)


class LMSUserEnrollView(APIView):
    """Enroll authenticated users in a published free course."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSEnrollThrottle]

    @extend_schema(
        operation_id="lms_user_course_enroll",
        tags=[TAG_LMS_USER],
        request=None,
        responses={
            200: ENROLLMENT_RESPONSE,
            201: ENROLLMENT_RESPONSE,
            403: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(
        self, request: Request, slug: str
    ) -> SuccessResponse | CreatedResponse | ErrorResponse:
        """Enroll current user in a course."""
        course = selectors.get_public_course_by_slug(slug)
        if course is None:
            return ErrorResponse(
                message="کلاس قابل ثبت‌نام یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        try:
            enrollment, created = services.enroll_user_in_course(user=request.user, course=course)
        except (LMSProfileIncompleteError, CourseNotEnrollabeError) as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        metadata = extract_audit_metadata(request)
        if created:
            log_action_async(
                user_id=request.user.pk,
                action=audit_actions.LMS_ENROLLMENT_CREATED,
                resource_type="lms_enrollment",
                resource_id=str(enrollment.pk),
                extra_data={"course_id": course.pk},
                **metadata,
            )
            return CreatedResponse(
                data=EnrollmentSerializer(enrollment).data, message="ثبت‌نام شما با موفقیت انجام شد."
            )
        return SuccessResponse(
            data=EnrollmentSerializer(enrollment).data,
            message="شما قبلاً در این کلاس ثبت‌نام کرده‌اید.",
        )


class LMSUserEnrollmentListView(APIView):
    """List current user's enrollments."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_enrollments_list",
        tags=[TAG_LMS_USER],
        responses={200: ENROLLMENT_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return current user's enrollments."""
        queryset = selectors.get_user_enrollments(user_id=request.user.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = EnrollmentSerializer(page, many=True)
        return paginator.get_paginated_response(
            serializer.data, message="لیست ثبت‌نام‌های شما دریافت شد."
        )


class LMSUserEnrollmentDetailView(APIView):
    """Retrieve one enrollment owned by the current user with progress records."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_enrollments_retrieve",
        tags=[TAG_LMS_USER],
        responses={200: ENROLLMENT_DETAIL_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, enrollment_id: int) -> SuccessResponse | ErrorResponse:
        """Return one owned enrollment."""
        enrollment = selectors.get_user_enrollment_by_id(
            user_id=request.user.pk,
            enrollment_id=enrollment_id,
        )
        if enrollment is None:
            return ErrorResponse(
                message="ثبت‌نامی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(data=EnrollmentDetailSerializer(enrollment).data)


class LMSLessonProgressUpdateView(APIView):
    """Update watch progress for a lesson in one of the user's enrollments."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSProgressThrottle]

    @extend_schema(
        operation_id="lms_user_lessons_progress_update",
        tags=[TAG_LMS_USER],
        request=LessonProgressUpdateSerializer,
        responses={
            200: LESSON_PROGRESS_RESPONSE,
            400: LMS_ERROR_RESPONSE,
            403: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, lesson_id: int) -> SuccessResponse | ErrorResponse:
        """Update lesson watch progress monotonically."""
        lesson = selectors.get_lesson_for_progress(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)

        enrollment = selectors.get_user_enrollment_for_course(
            user_id=request.user.pk,
            course_id=lesson.course_id,
        )
        if enrollment is None:
            return ErrorResponse(
                message="برای ثبت پیشرفت ابتدا باید در کلاس ثبت‌نام کنید.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = LessonProgressUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            progress = services.update_lesson_progress(
                enrollment=enrollment,
                lesson=lesson,
                watched_seconds=serializer.validated_data["watched_seconds"],
                last_position_seconds=serializer.validated_data.get("last_position_seconds"),
            )
        except (EnrollmentNotActiveError, LessonNotInEnrollmentCourseError) as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_400_BAD_REQUEST)

        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_PROGRESS_UPDATED,
            resource_type="lms_lesson_progress",
            resource_id=str(progress.pk),
            extra_data={
                "lesson_id": lesson.pk,
                "course_id": lesson.course_id,
                "progress_percent": str(progress.progress_percent),
            },
            **extract_audit_metadata(request),
        )
        return SuccessResponse(
            data=LessonProgressSerializer(progress).data,
            message="پیشرفت جلسه با موفقیت ثبت شد.",
        )


class LMSUserLearningRecommendationView(APIView):
    """User endpoint for personalized LMS course recommendations."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_learning_recommendations",
        tags=[TAG_LMS_USER],
        responses={200: LEARNING_RECOMMENDATION_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return ranked course recommendations for the authenticated user."""
        raw_limit = request.query_params.get("limit", "10")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 10
        recommendations = selectors.get_user_learning_recommendations(
            user_id=request.user.pk, limit=limit
        )
        return SuccessResponse(
            data=LearningRecommendationItemSerializer(recommendations, many=True).data,
            message="پیشنهادهای یادگیری با موفقیت دریافت شد.",
        )


class LMSAdminLearningRecommendationOverviewView(APIView):
    """Admin overview for recommendation readiness and cold-start courses."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_learning_recommendations_overview",
        tags=[TAG_LMS_ADMIN],
        responses={200: LEARNING_RECOMMENDATION_OVERVIEW_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return aggregate recommendation overview for admins."""
        raw_limit = request.query_params.get("limit", "10")
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 10
        overview = selectors.get_admin_learning_recommendation_overview(limit=limit)
        return SuccessResponse(data=LearningRecommendationOverviewSerializer(overview).data)


class LMSUserSkillListView(APIView):
    """List skills/badges visible in the current user's profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="lms_user_skills_list",
        tags=[TAG_LMS_USER],
        responses={200: SKILL_LIST_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return LMS skills for the current user."""
        skills = selectors.get_user_skills(user_id=request.user.pk)
        return SuccessResponse(data=LMSUserSkillSerializer(skills, many=True).data)


class LMSLessonMediaAccessView(APIView):
    """Return signed/CDN-ready media URL for an enrolled user's lesson."""

    permission_classes = [IsAuthenticated]
    serializer_class = LessonMediaAccessSerializer

    @extend_schema(
        operation_id="lms_user_lessons_media_access",
        tags=[TAG_LMS_USER],
        responses={200: LESSON_MEDIA_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(
        self, request: Request, lesson_id: int, media_kind: str
    ) -> SuccessResponse | ErrorResponse:
        """Return access payload for lesson video or attachment."""
        lesson = selectors.get_lesson_for_progress(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            payload = services.build_lesson_media_access(
                lesson=lesson, user=request.user, media_kind=media_kind
            )
        except LessonMediaAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        except LessonMediaUnavailableError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_404_NOT_FOUND)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_LESSON_MEDIA_ACCESSED,
            resource_type="lms_lesson",
            resource_id=str(lesson.pk),
            extra_data={"course_id": lesson.course_id, "media_kind": media_kind},
            **extract_audit_metadata(request),
        )
        return SuccessResponse(data=payload, message="دسترسی رسانه جلسه صادر شد.")


class LMSAdminLearningActivityStatementListView(APIView):
    """Admin list endpoint for xAPI-like learning activity statements."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_learning_activity_statements_list",
        tags=[TAG_LMS_ADMIN],
        responses={200: LEARNING_STATEMENT_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return paginated learning activity statements for analytics/export readiness."""
        queryset = selectors.get_admin_learning_activity_statements()
        verb = request.query_params.get("verb")
        if verb:
            queryset = queryset.filter(verb=verb)
        course_id = request.query_params.get("course")
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = LearningActivityStatementSerializer(page, many=True)
        return paginator.get_paginated_response(
            serializer.data, message="Statementهای یادگیری با موفقیت دریافت شد."
        )
