"""گروه دامنه‌ای `views_catalog_admin` از views — فاز ۱۱ (تفکیک P3-16).

کلاس‌ها عیناً منتقل شده‌اند؛ مشترکات از views_common؛ نامِ عمومیِ این گروه‌ها را فقط از facade (apps.*.views) یا همین ماژول import کنید.
"""

from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, DeletedResponse, ErrorResponse, SuccessResponse
from apps.core.schemas import (
    build_success_response_serializer,
)
from apps.lms import selectors, services
from apps.lms.export import build_course_enrollments_workbook, build_course_export_filename
from apps.lms.filters import (
    CourseAdminFilter,
    CourseReportEnrollmentFilter,
    LMSCategoryAdminFilter,
)
from apps.lms.permissions import IsLMSAdminUser
from apps.lms.serializers import (
    CourseCreateUpdateSerializer,
    CourseDetailSerializer,
    CourseReportSerializer,
    CourseSummarySerializer,
    LessonCreateUpdateSerializer,
    LessonSummarySerializer,
    LessonVideoProcessingJobSerializer,
    LMSCategoryCreateUpdateSerializer,
    LMSCategorySerializer,
)
from apps.lms.services import (
    VideoProcessingJobError,
    request_lesson_video_processing,
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


class LMSAdminCategoryListCreateView(APIView):
    """Admin list/create categories."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_categories_list",
        tags=[TAG_LMS_ADMIN],
        responses={200: CATEGORY_LIST_RESPONSE, 403: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request) -> SuccessResponse:
        """Return all categories for admin."""
        queryset = selectors.get_admin_categories()
        filterset = LMSCategoryAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        return SuccessResponse(data=LMSCategorySerializer(queryset, many=True).data)

    @extend_schema(
        operation_id="lms_admin_categories_create",
        tags=[TAG_LMS_ADMIN],
        request=LMSCategoryCreateUpdateSerializer,
        responses={201: CATEGORY_RESPONSE, 400: LMS_ERROR_RESPONSE, 403: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request) -> CreatedResponse:
        """Create a category."""
        serializer = LMSCategoryCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = services.create_category(**serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_CATEGORY_CREATED,
            resource_type="lms_category",
            resource_id=str(category.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=LMSCategorySerializer(category).data, message="دسته‌بندی با موفقیت ساخته شد."
        )


class LMSAdminCategoryDetailView(APIView):
    """Admin retrieve/update/delete category."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_categories_retrieve",
        tags=[TAG_LMS_ADMIN],
        responses={200: CATEGORY_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Return one category for admin."""
        category = selectors.get_admin_category_by_id(category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=404)
        return SuccessResponse(data=LMSCategorySerializer(category).data)

    @extend_schema(
        operation_id="lms_admin_categories_update",
        tags=[TAG_LMS_ADMIN],
        request=LMSCategoryCreateUpdateSerializer,
        responses={200: CATEGORY_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def patch(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Update category."""
        category = selectors.get_admin_category_by_id(category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=404)
        serializer = LMSCategoryCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        category = services.update_category(category=category, **serializer.validated_data)
        return SuccessResponse(
            data=LMSCategorySerializer(category).data, message="دسته‌بندی بروزرسانی شد."
        )

    @extend_schema(
        operation_id="lms_admin_categories_delete",
        tags=[TAG_LMS_ADMIN],
        responses={
            200: build_success_response_serializer(name="LMSCategoryDeletedResponse"),
            404: LMS_ERROR_RESPONSE,
        },
    )
    def delete(self, request: Request, category_id: int) -> DeletedResponse | ErrorResponse:
        """Soft-delete category."""
        category = selectors.get_admin_category_by_id(category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=404)
        services.delete_category(category=category)
        return DeletedResponse(message="دسته‌بندی غیرفعال شد.")


class LMSAdminCourseListCreateView(APIView):
    """Admin list/create courses."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_courses_list",
        tags=[TAG_LMS_ADMIN],
        responses={200: COURSE_LIST_RESPONSE},
    )
    def get(self, request: Request) -> Response:
        """Return admin course list."""
        queryset = selectors.get_admin_courses()
        filterset = CourseAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CourseSummarySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="lms_admin_courses_create",
        tags=[TAG_LMS_ADMIN],
        request=CourseCreateUpdateSerializer,
        responses={201: COURSE_RESPONSE, 400: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request) -> CreatedResponse:
        """Create draft course."""
        serializer = CourseCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = services.create_course(**serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_COURSE_CREATED,
            resource_type="lms_course",
            resource_id=str(course.pk),
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=CourseDetailSerializer(course).data, message="کلاس با موفقیت ساخته شد."
        )


class LMSAdminCourseDetailView(APIView):
    """Admin retrieve/update/delete course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_courses_retrieve",
        tags=[TAG_LMS_ADMIN],
        responses={200: COURSE_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Return one course for admin."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        return SuccessResponse(data=CourseDetailSerializer(course).data)

    @extend_schema(
        operation_id="lms_admin_courses_update",
        tags=[TAG_LMS_ADMIN],
        request=CourseCreateUpdateSerializer,
        responses={200: COURSE_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def patch(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Update course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        serializer = CourseCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        course = services.update_course(course=course, **serializer.validated_data)
        return SuccessResponse(
            data=CourseDetailSerializer(course).data, message="کلاس بروزرسانی شد."
        )

    @extend_schema(
        operation_id="lms_admin_courses_delete",
        tags=[TAG_LMS_ADMIN],
        responses={
            200: build_success_response_serializer(name="LMSCourseDeletedResponse"),
            404: LMS_ERROR_RESPONSE,
        },
    )
    def delete(self, request: Request, course_id: int) -> DeletedResponse | ErrorResponse:
        """Soft-delete course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        services.delete_course(course=course)
        return DeletedResponse(message="کلاس غیرفعال شد.")


class LMSAdminCoursePublishView(APIView):
    """Admin publish course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_courses_publish",
        tags=[TAG_LMS_ADMIN],
        request=None,
        responses={200: COURSE_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Publish course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        course = services.publish_course(course=course)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_COURSE_PUBLISHED,
            resource_type="lms_course",
            resource_id=str(course.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(data=CourseDetailSerializer(course).data, message="کلاس منتشر شد.")


class LMSAdminCourseArchiveView(APIView):
    """Admin archive course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_courses_archive",
        tags=[TAG_LMS_ADMIN],
        request=None,
        responses={200: COURSE_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Archive course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        course = services.archive_course(course=course)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_COURSE_ARCHIVED,
            resource_type="lms_course",
            resource_id=str(course.pk),
            **extract_audit_metadata(request),
        )
        return SuccessResponse(data=CourseDetailSerializer(course).data, message="کلاس آرشیو شد.")


class LMSAdminLessonListCreateView(APIView):
    """Admin list/create lessons for a course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_lessons_list",
        tags=[TAG_LMS_ADMIN],
        responses={200: LESSON_LIST_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Return all lessons for admin."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        lessons = selectors.get_course_lessons(course=course, public_only=False)
        return SuccessResponse(data=LessonSummarySerializer(lessons, many=True).data)

    @extend_schema(
        operation_id="lms_admin_lessons_create",
        tags=[TAG_LMS_ADMIN],
        request=LessonCreateUpdateSerializer,
        responses={201: LESSON_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def post(self, request: Request, course_id: int) -> CreatedResponse | ErrorResponse:
        """Create lesson."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        serializer = LessonCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lesson = services.create_lesson(course=course, **serializer.validated_data)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_LESSON_CREATED,
            resource_type="lms_lesson",
            resource_id=str(lesson.pk),
            extra_data={"course_id": course.pk},
            **extract_audit_metadata(request),
        )
        return CreatedResponse(data=LessonSummarySerializer(lesson).data, message="جلسه ساخته شد.")


class LMSAdminLessonDetailView(APIView):
    """Admin update/delete lesson."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_lessons_update",
        tags=[TAG_LMS_ADMIN],
        request=LessonCreateUpdateSerializer,
        responses={200: LESSON_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def patch(self, request: Request, lesson_id: int) -> SuccessResponse | ErrorResponse:
        """Update lesson."""
        lesson = selectors.get_admin_lesson_by_id(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=404)
        serializer = LessonCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lesson = services.update_lesson(lesson=lesson, **serializer.validated_data)
        return SuccessResponse(
            data=LessonSummarySerializer(lesson).data, message="جلسه بروزرسانی شد."
        )

    @extend_schema(
        operation_id="lms_admin_lessons_delete",
        tags=[TAG_LMS_ADMIN],
        responses={
            200: build_success_response_serializer(name="LMSLessonDeletedResponse"),
            404: LMS_ERROR_RESPONSE,
        },
    )
    def delete(self, request: Request, lesson_id: int) -> DeletedResponse | ErrorResponse:
        """Soft-delete lesson."""
        lesson = selectors.get_admin_lesson_by_id(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=404)
        services.delete_lesson(lesson=lesson)
        return DeletedResponse(message="جلسه غیرفعال شد.")


class LMSAdminLessonVideoProcessingView(APIView):
    """Admin endpoint to queue lesson video processing."""

    permission_classes = [IsLMSAdminUser]
    serializer_class = LessonVideoProcessingJobSerializer

    @extend_schema(
        operation_id="lms_admin_lessons_video_processing_create",
        tags=[TAG_LMS_ADMIN],
        request=None,
        responses={
            201: VIDEO_PROCESSING_JOB_RESPONSE,
            400: LMS_ERROR_RESPONSE,
            404: LMS_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request, lesson_id: int) -> CreatedResponse | ErrorResponse:
        """Queue video processing for an uploaded lesson video."""
        lesson = selectors.get_admin_lesson_by_id(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            job = request_lesson_video_processing(lesson=lesson, requested_by=request.user)
        except VideoProcessingJobError as exc:
            return ErrorResponse(message=str(exc))
        from apps.lms.tasks import process_lesson_video_job_task

        process_lesson_video_job_task.delay(job_id=job.pk)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_VIDEO_PROCESSING_REQUESTED,
            resource_type="lms_lesson_video_processing_job",
            resource_id=str(job.pk),
            extra_data={
                "lesson_id": lesson.pk,
                "course_id": lesson.course_id,
                "status": job.status,
            },
            **extract_audit_metadata(request),
        )
        return CreatedResponse(
            data=LessonVideoProcessingJobSerializer(job).data,
            message="پردازش ویدئوی جلسه در صف قرار گرفت.",
        )


class LMSAdminLessonVideoProcessingStatusView(APIView):
    """Admin endpoint to inspect latest lesson video processing job."""

    permission_classes = [IsLMSAdminUser]
    serializer_class = LessonVideoProcessingJobSerializer

    @extend_schema(
        operation_id="lms_admin_lessons_video_processing_status",
        tags=[TAG_LMS_ADMIN],
        responses={200: VIDEO_PROCESSING_JOB_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, lesson_id: int) -> SuccessResponse | ErrorResponse:
        """Return latest video processing job for a lesson."""
        lesson = selectors.get_admin_lesson_by_id(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        job = lesson.video_processing_jobs.order_by("-created_at").first()
        if job is None:
            return ErrorResponse(
                message="برای این جلسه job پردازش ویدئو ثبت نشده است.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return SuccessResponse(
            data=LessonVideoProcessingJobSerializer(job).data,
            message="وضعیت پردازش ویدئو دریافت شد.",
        )


class LMSAdminCourseReportView(APIView):
    """Admin detailed report for one course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_courses_report",
        tags=[TAG_LMS_ADMIN],
        responses={200: COURSE_REPORT_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Return course report rows and summary."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        enrollments = selectors.get_course_report_queryset(course_id=course.pk)
        filterset = CourseReportEnrollmentFilter(request.query_params, queryset=enrollments)
        if filterset.is_valid():
            enrollments = filterset.qs
        summary = {
            "participants_count": enrollments.count(),
            "graduates_count": enrollments.filter(certificate__isnull=False).count(),
            "active_count": enrollments.filter(status="active").count(),
        }
        return SuccessResponse(
            data=CourseReportSerializer(
                {"course": course, "summary": summary, "enrollments": enrollments}
            ).data,
            message="گزارش کلاس با موفقیت دریافت شد.",
        )


class LMSAdminCourseAnalyticsView(APIView):
    """Admin analytics summary for one course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_courses_analytics",
        tags=[TAG_LMS_ADMIN],
        responses={200: COURSE_ANALYTICS_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Return aggregate analytics for a course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(
            data=selectors.get_course_analytics(course=course),
            message="تحلیل کلاس با موفقیت دریافت شد.",
        )


class LMSAdminCourseLeaderboardView(APIView):
    """Admin leaderboard for one course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_courses_leaderboard",
        tags=[TAG_LMS_ADMIN],
        responses={200: COURSE_LEADERBOARD_RESPONSE, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Return top learners ranked by score/progress/badge."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(
            data=selectors.get_course_leaderboard(course=course),
            message="رتبه‌بندی کلاس با موفقیت دریافت شد.",
        )


class LMSAdminCourseExportView(APIView):
    """Admin Excel export for course participants."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(
        operation_id="lms_admin_courses_export",
        tags=[TAG_LMS_ADMIN],
        responses={200: None, 404: LMS_ERROR_RESPONSE},
    )
    def get(self, request: Request, course_id: int) -> HttpResponse | ErrorResponse:
        """Export course enrollment report as Excel."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        enrollments = selectors.get_course_report_queryset(course_id=course.pk)
        workbook = build_course_enrollments_workbook(course=course, enrollments=enrollments)
        filename = build_course_export_filename(course=course)
        log_action_async(
            user_id=request.user.pk,
            action=audit_actions.LMS_COURSE_REPORT_EXPORTED,
            resource_type="lms_course",
            resource_id=str(course.pk),
            extra_data={"filename": filename},
            **extract_audit_metadata(request),
        )
        response = HttpResponse(
            workbook.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
