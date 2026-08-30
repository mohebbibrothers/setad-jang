"""گروه دامنه‌ای `views_public_catalog` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api_cache import build_cache_variant, cached_public_payload
from apps.core.pagination import StandardPagination
from apps.core.responses import ErrorResponse, SuccessResponse
from apps.lms import selectors
from apps.lms.filters import (
    CoursePublicFilter,
)
from apps.lms.serializers import (
    CourseDetailSerializer,
    CourseSummarySerializer,
    LessonSummarySerializer,
    LMSCategorySerializer,
)
from apps.lms.throttles import (
    LMSBrowseAnonThrottle,
    LMSBrowseUserThrottle,
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


class LMSCategoryPublicListView(APIView):
    """Public list of active LMS categories."""

    permission_classes = [AllowAny]
    # یافتهٔ ممیزی ۵.۱: برداشت انبوه محتوا — browse با throttle اختصاصی.
    throttle_classes = [LMSBrowseAnonThrottle, LMSBrowseUserThrottle]

    @extend_schema(
        operation_id="lms_public_categories_list",
        tags=[TAG_LMS_PUBLIC],
        responses={200: CATEGORY_LIST_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return active categories."""
        payload = cached_public_payload(
            domain="lms",
            namespace="lms:categories",
            parts=("categories",),
            factory=lambda: LMSCategorySerializer(
                selectors.get_public_categories(), many=True
            ).data,
        )
        return SuccessResponse(data=payload)


class LMSCategoryPublicDetailView(APIView):
    """Public category detail by slug."""

    permission_classes = [AllowAny]
    # یافتهٔ ممیزی ۵.۱: برداشت انبوه محتوا — browse با throttle اختصاصی.
    throttle_classes = [LMSBrowseAnonThrottle, LMSBrowseUserThrottle]

    @extend_schema(
        operation_id="lms_public_categories_retrieve",
        tags=[TAG_LMS_PUBLIC],
        responses={200: CATEGORY_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return one public category."""

        def build_payload() -> dict | None:
            category = selectors.get_public_category_by_slug(slug)
            if category is None:
                return None
            return LMSCategorySerializer(category).data

        payload = cached_public_payload(
            domain="lms",
            namespace="lms:public_detail",
            parts=("category", slug),
            factory=build_payload,
        )
        if payload is None:
            return ErrorResponse(
                message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(data=payload)


class LMSCoursePublicListView(APIView):
    """Public list of published LMS courses."""

    permission_classes = [AllowAny]
    # یافتهٔ ممیزی ۵.۱: برداشت انبوه محتوا — browse با throttle اختصاصی.
    throttle_classes = [LMSBrowseAnonThrottle, LMSBrowseUserThrottle]

    @extend_schema(
        operation_id="lms_public_courses_list",
        tags=[TAG_LMS_PUBLIC],
        responses={200: COURSE_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return paginated public course catalog."""
        base_queryset = selectors.get_public_courses()
        filterset = CoursePublicFilter(request.query_params, queryset=base_queryset)

        def build_payload() -> dict:
            queryset = filterset.qs if filterset.is_valid() else base_queryset
            paginator = StandardPagination()
            page = paginator.paginate_queryset(queryset, request, view=self)
            serializer = CourseSummarySerializer(page, many=True)
            response = paginator.get_paginated_response(
                serializer.data, message="لیست کلاس‌ها با موفقیت دریافت شد."
            )
            return response.data["data"]

        payload = cached_public_payload(
            domain="lms",
            namespace="lms:public_list",
            parts=(
                "courses",
                *build_cache_variant(
                    request, filterset=filterset, pagination_class=StandardPagination
                ),
            ),
            factory=build_payload,
        )
        return SuccessResponse(data=payload, message="لیست کلاس‌ها با موفقیت دریافت شد.")


class LMSCoursePublicDetailView(APIView):
    """Public course detail by slug."""

    permission_classes = [AllowAny]
    # یافتهٔ ممیزی ۵.۱: برداشت انبوه محتوا — browse با throttle اختصاصی.
    throttle_classes = [LMSBrowseAnonThrottle, LMSBrowseUserThrottle]

    @extend_schema(
        operation_id="lms_public_courses_retrieve",
        tags=[TAG_LMS_PUBLIC],
        responses={200: COURSE_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return one published course."""

        def build_payload() -> dict | None:
            course = selectors.get_public_course_by_slug(slug)
            if course is None:
                return None
            return CourseDetailSerializer(course).data

        payload = cached_public_payload(
            domain="lms",
            namespace="lms:public_detail",
            parts=("course", slug),
            factory=build_payload,
        )
        if payload is None:
            return ErrorResponse(
                message="کلاسی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND
            )
        return SuccessResponse(data=payload)


class LMSCourseLessonsPublicView(APIView):
    """Public lesson list for a published course."""

    permission_classes = [AllowAny]
    # یافتهٔ ممیزی ۵.۱: برداشت انبوه محتوا — browse با throttle اختصاصی.
    throttle_classes = [LMSBrowseAnonThrottle, LMSBrowseUserThrottle]

    @extend_schema(
        operation_id="lms_public_course_lessons_list",
        tags=[TAG_LMS_PUBLIC],
        responses={200: LESSON_LIST_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return public lessons for a course."""

        def build_payload() -> list | None:
            course = selectors.get_public_course_by_slug(slug)
            if course is None:
                return None
            lessons = selectors.get_course_lessons(course=course)
            return LessonSummarySerializer(lessons, many=True).data

        payload = cached_public_payload(
            domain="lms",
            namespace="lms:public_list",
            parts=("lessons", slug),
            factory=build_payload,
        )
        if payload is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=payload)


class LMSLessonPublicDetailView(APIView):
    """Public lesson detail for previews or course catalog."""

    permission_classes = [AllowAny]
    # یافتهٔ ممیزی ۵.۱: برداشت انبوه محتوا — browse با throttle اختصاصی.
    throttle_classes = [LMSBrowseAnonThrottle, LMSBrowseUserThrottle]

    @extend_schema(
        operation_id="lms_public_lessons_retrieve",
        tags=[TAG_LMS_PUBLIC],
        responses={200: LESSON_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, slug: str, lesson_slug: str) -> SuccessResponse | ErrorResponse:
        """Return one public lesson."""

        def build_payload() -> dict | None:
            course = selectors.get_public_course_by_slug(slug)
            if course is None:
                return None
            lesson = selectors.get_lesson_by_slug(course=course, lesson_slug=lesson_slug)
            if lesson is None:
                return None
            return LessonSummarySerializer(lesson).data

        payload = cached_public_payload(
            domain="lms",
            namespace="lms:public_detail",
            parts=("lesson", slug, lesson_slug),
            factory=build_payload,
        )
        if payload is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=payload)
