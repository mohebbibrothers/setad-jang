"""API views for LMS public catalog, admin course management, and user enrollment."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit_logs import actions as audit_actions
from apps.audit_logs.helpers import extract_audit_metadata
from apps.audit_logs.services import log_action_async
from apps.core.pagination import StandardPagination
from apps.core.responses import CreatedResponse, DeletedResponse, ErrorResponse, SuccessResponse
from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)
from apps.lms import selectors, services
from apps.lms.filters import (
    CourseAdminFilter,
    CoursePublicFilter,
    CourseReportEnrollmentFilter,
    LMSCategoryAdminFilter,
)
from apps.lms.permissions import IsLMSAdminUser
from apps.lms.serializers import (
    CourseCreateUpdateSerializer,
    CourseDetailSerializer,
    CourseReportSerializer,
    CourseSummarySerializer,
    DiscussionModerationSerializer,
    DiscussionReportCreateSerializer,
    DiscussionReportReviewSerializer,
    DiscussionReportSerializer,
    EnrollmentDetailSerializer,
    EnrollmentSerializer,
    LessonAnswerCreateSerializer,
    LessonAnswerSerializer,
    LessonCreateUpdateSerializer,
    LessonProgressSerializer,
    LessonProgressUpdateSerializer,
    LessonQuestionCreateSerializer,
    LessonQuestionSerializer,
    LessonSummarySerializer,
    LMSCategoryCreateUpdateSerializer,
    LMSCategorySerializer,
    LMSUserSkillSerializer,
)
from apps.lms.services import (
    CourseNotEnrollabeError,
    EnrollmentNotActiveError,
    LessonNotInEnrollmentCourseError,
    LMSDiscussionAccessError,
    LMSDiscussionModerationError,
    LMSProfileIncompleteError,
)
from apps.lms.throttles import LMSDiscussionThrottle, LMSEnrollThrottle, LMSProgressThrottle

TAG_LMS_PUBLIC = "آموزش — عمومی"
TAG_LMS_USER = "آموزش — کاربر"
TAG_LMS_ADMIN = "آموزش — مدیریت"

LMS_ERROR_RESPONSE = build_error_response_serializer(name="LMSErrorResponse")
CATEGORY_RESPONSE = build_success_response_serializer(name="LMSCategoryResponse", data_serializer=LMSCategorySerializer)
CATEGORY_LIST_RESPONSE = build_success_response_serializer(name="LMSCategoryListResponse", data_serializer=LMSCategorySerializer, many=True)
COURSE_RESPONSE = build_success_response_serializer(name="LMSCourseResponse", data_serializer=CourseDetailSerializer)
COURSE_LIST_RESPONSE = build_paginated_success_response_serializer(name="LMSCourseListResponse", item_serializer=CourseSummarySerializer)
LESSON_RESPONSE = build_success_response_serializer(name="LMSLessonResponse", data_serializer=LessonSummarySerializer)
LESSON_LIST_RESPONSE = build_success_response_serializer(name="LMSLessonListResponse", data_serializer=LessonSummarySerializer, many=True)
ENROLLMENT_RESPONSE = build_success_response_serializer(name="LMSEnrollmentResponse", data_serializer=EnrollmentSerializer)
ENROLLMENT_DETAIL_RESPONSE = build_success_response_serializer(name="LMSEnrollmentDetailResponse", data_serializer=EnrollmentDetailSerializer)
ENROLLMENT_LIST_RESPONSE = build_paginated_success_response_serializer(name="LMSEnrollmentListResponse", item_serializer=EnrollmentSerializer)
LESSON_PROGRESS_RESPONSE = build_success_response_serializer(name="LMSLessonProgressResponse", data_serializer=LessonProgressSerializer)
QUESTION_RESPONSE = build_success_response_serializer(name="LMSLessonQuestionResponse", data_serializer=LessonQuestionSerializer)
QUESTION_LIST_RESPONSE = build_paginated_success_response_serializer(name="LMSLessonQuestionListResponse", item_serializer=LessonQuestionSerializer)
ANSWER_RESPONSE = build_success_response_serializer(name="LMSLessonAnswerResponse", data_serializer=LessonAnswerSerializer)
DISCUSSION_REPORT_RESPONSE = build_success_response_serializer(name="LMSDiscussionReportResponse", data_serializer=DiscussionReportSerializer)
DISCUSSION_REPORT_LIST_RESPONSE = build_paginated_success_response_serializer(name="LMSDiscussionReportListResponse", item_serializer=DiscussionReportSerializer)
SKILL_LIST_RESPONSE = build_success_response_serializer(name="LMSSkillListResponse", data_serializer=LMSUserSkillSerializer, many=True)
COURSE_REPORT_RESPONSE = build_success_response_serializer(name="LMSCourseReportResponse", data_serializer=CourseReportSerializer)


class LMSCategoryPublicListView(APIView):
    """Public list of active LMS categories."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="lms_public_categories_list", tags=[TAG_LMS_PUBLIC], responses={200: CATEGORY_LIST_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return active categories."""
        categories = selectors.get_public_categories()
        return SuccessResponse(data=LMSCategorySerializer(categories, many=True).data)


class LMSCategoryPublicDetailView(APIView):
    """Public category detail by slug."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="lms_public_categories_retrieve", tags=[TAG_LMS_PUBLIC], responses={200: CATEGORY_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return one public category."""
        category = selectors.get_public_category_by_slug(slug)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=LMSCategorySerializer(category).data)


class LMSCoursePublicListView(APIView):
    """Public list of published LMS courses."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="lms_public_courses_list", tags=[TAG_LMS_PUBLIC], responses={200: COURSE_LIST_RESPONSE})
    def get(self, request: Request) -> Response:
        """Return paginated public course catalog."""
        queryset = selectors.get_public_courses()
        filterset = CoursePublicFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CourseSummarySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data, message="لیست کلاس‌ها با موفقیت دریافت شد.")


class LMSCoursePublicDetailView(APIView):
    """Public course detail by slug."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="lms_public_courses_retrieve", tags=[TAG_LMS_PUBLIC], responses={200: COURSE_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return one published course."""
        course = selectors.get_public_course_by_slug(slug)
        if course is None:
            return ErrorResponse(message="کلاسی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=CourseDetailSerializer(course).data)


class LMSCourseLessonsPublicView(APIView):
    """Public lesson list for a published course."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="lms_public_course_lessons_list", tags=[TAG_LMS_PUBLIC], responses={200: LESSON_LIST_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, slug: str) -> SuccessResponse | ErrorResponse:
        """Return public lessons for a course."""
        course = selectors.get_public_course_by_slug(slug)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        lessons = selectors.get_course_lessons(course=course)
        return SuccessResponse(data=LessonSummarySerializer(lessons, many=True).data)


class LMSLessonPublicDetailView(APIView):
    """Public lesson detail for previews or course catalog."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="lms_public_lessons_retrieve", tags=[TAG_LMS_PUBLIC], responses={200: LESSON_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, slug: str, lesson_slug: str) -> SuccessResponse | ErrorResponse:
        """Return one public lesson."""
        course = selectors.get_public_course_by_slug(slug)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        lesson = selectors.get_lesson_by_slug(course=course, lesson_slug=lesson_slug)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=LessonSummarySerializer(lesson).data)


class LMSUserEnrollView(APIView):
    """Enroll authenticated users in a published free course."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSEnrollThrottle]

    @extend_schema(operation_id="lms_user_course_enroll", tags=[TAG_LMS_USER], request=None, responses={200: ENROLLMENT_RESPONSE, 201: ENROLLMENT_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, slug: str) -> SuccessResponse | CreatedResponse | ErrorResponse:
        """Enroll current user in a course."""
        course = selectors.get_public_course_by_slug(slug)
        if course is None:
            return ErrorResponse(message="کلاس قابل ثبت‌نام یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
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
            return CreatedResponse(data=EnrollmentSerializer(enrollment).data, message="ثبت‌نام شما با موفقیت انجام شد.")
        return SuccessResponse(data=EnrollmentSerializer(enrollment).data, message="شما قبلاً در این کلاس ثبت‌نام کرده‌اید.")


class LMSUserEnrollmentListView(APIView):
    """List current user's enrollments."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="lms_user_enrollments_list", tags=[TAG_LMS_USER], responses={200: ENROLLMENT_LIST_RESPONSE})
    def get(self, request: Request) -> Response:
        """Return current user's enrollments."""
        queryset = selectors.get_user_enrollments(user_id=request.user.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = EnrollmentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data, message="لیست ثبت‌نام‌های شما دریافت شد.")


class LMSUserEnrollmentDetailView(APIView):
    """Retrieve one enrollment owned by the current user with progress records."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="lms_user_enrollments_retrieve", tags=[TAG_LMS_USER], responses={200: ENROLLMENT_DETAIL_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, enrollment_id: int) -> SuccessResponse | ErrorResponse:
        """Return one owned enrollment."""
        enrollment = selectors.get_user_enrollment_by_id(
            user_id=request.user.pk,
            enrollment_id=enrollment_id,
        )
        if enrollment is None:
            return ErrorResponse(message="ثبت‌نامی با این شناسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return SuccessResponse(data=EnrollmentDetailSerializer(enrollment).data)


class LMSLessonProgressUpdateView(APIView):
    """Update watch progress for a lesson in one of the user's enrollments."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSProgressThrottle]

    @extend_schema(operation_id="lms_user_lessons_progress_update", tags=[TAG_LMS_USER], request=LessonProgressUpdateSerializer, responses={200: LESSON_PROGRESS_RESPONSE, 400: LMS_ERROR_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
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
            return ErrorResponse(message="برای ثبت پیشرفت ابتدا باید در کلاس ثبت‌نام کنید.", status_code=status.HTTP_403_FORBIDDEN)

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


class LMSUserSkillListView(APIView):
    """List skills/badges visible in the current user's profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="lms_user_skills_list", tags=[TAG_LMS_USER], responses={200: SKILL_LIST_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return LMS skills for the current user."""
        skills = selectors.get_user_skills(user_id=request.user.pk)
        return SuccessResponse(data=LMSUserSkillSerializer(skills, many=True).data)


class LMSLessonQuestionListCreateView(APIView):
    """List questions for a lesson and allow enrolled users to ask immediately."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSDiscussionThrottle]

    @extend_schema(operation_id="lms_lesson_questions_list", tags=[TAG_LMS_USER], responses={200: QUESTION_LIST_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, lesson_id: int) -> Response:
        """Return lesson questions for enrolled users."""
        lesson = selectors.get_lesson_for_progress(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            services.ensure_user_enrolled_for_lesson(user=request.user, lesson=lesson)
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        queryset = selectors.get_lesson_questions(lesson_id=lesson.pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = LessonQuestionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data, message="پرسش‌های جلسه با موفقیت دریافت شد.")

    @extend_schema(operation_id="lms_lesson_questions_create", tags=[TAG_LMS_USER], request=LessonQuestionCreateSerializer, responses={201: QUESTION_RESPONSE, 400: LMS_ERROR_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, lesson_id: int) -> CreatedResponse | ErrorResponse:
        """Create a visible question under a lesson."""
        lesson = selectors.get_lesson_for_progress(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = LessonQuestionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            question = services.create_lesson_question(
                lesson=lesson,
                user=request.user,
                title=serializer.validated_data["title"],
                body=serializer.validated_data["body"],
            )
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.LMS_QUESTION_CREATED, resource_type="lms_lesson_question", resource_id=str(question.pk), extra_data={"lesson_id": lesson.pk, "course_id": lesson.course_id}, **extract_audit_metadata(request))
        return CreatedResponse(data=LessonQuestionSerializer(question).data, message="سؤال شما با موفقیت ثبت شد.")


class LMSQuestionAnswerCreateView(APIView):
    """Create answer for a lesson question."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSDiscussionThrottle]

    @extend_schema(operation_id="lms_question_answers_create", tags=[TAG_LMS_USER], request=LessonAnswerCreateSerializer, responses={201: ANSWER_RESPONSE, 400: LMS_ERROR_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, question_id: int) -> CreatedResponse | ErrorResponse:
        """Create an answer under an existing question."""
        question = selectors.get_lesson_question_by_id(question_id=question_id)
        if question is None:
            return ErrorResponse(message="سؤال یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = LessonAnswerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            answer = services.create_lesson_answer(
                question=question,
                user=request.user,
                body=serializer.validated_data["body"],
                is_instructor_answer=bool(request.user.is_staff or request.user.is_superuser),
            )
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.LMS_ANSWER_CREATED, resource_type="lms_lesson_answer", resource_id=str(answer.pk), extra_data={"question_id": question.pk}, **extract_audit_metadata(request))
        return CreatedResponse(data=LessonAnswerSerializer(answer).data, message="پاسخ با موفقیت ثبت شد.")


class LMSQuestionAcceptAnswerView(APIView):
    """Accept an answer for a question by owner or admin."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="lms_question_answers_accept", tags=[TAG_LMS_USER], request=None, responses={200: ANSWER_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, question_id: int, answer_id: int) -> SuccessResponse | ErrorResponse:
        """Mark answer as accepted."""
        question = selectors.get_lesson_question_by_id(question_id=question_id)
        answer = selectors.get_lesson_answer_by_id(answer_id=answer_id)
        if question is None or answer is None:
            return ErrorResponse(message="سؤال یا پاسخ یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        try:
            answer = services.accept_lesson_answer(question=question, answer=answer, user=request.user)
        except (LMSDiscussionAccessError, LMSDiscussionModerationError) as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        return SuccessResponse(data=LessonAnswerSerializer(answer).data, message="پاسخ به‌عنوان پاسخ پذیرفته‌شده ثبت شد.")


class LMSQuestionReportView(APIView):
    """Report a lesson question for moderation."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSDiscussionThrottle]

    @extend_schema(operation_id="lms_questions_report", tags=[TAG_LMS_USER], request=DiscussionReportCreateSerializer, responses={201: DISCUSSION_REPORT_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, question_id: int) -> CreatedResponse | ErrorResponse:
        """Report a question."""
        question = selectors.get_lesson_question_by_id(question_id=question_id)
        if question is None:
            return ErrorResponse(message="سؤال یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            report = services.report_lesson_question(question=question, reported_by=request.user, **serializer.validated_data)
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.LMS_DISCUSSION_REPORTED, resource_type="lms_discussion_report", resource_id=str(report.pk), extra_data={"question_id": question.pk}, **extract_audit_metadata(request))
        return CreatedResponse(data=DiscussionReportSerializer(report).data, message="گزارش شما ثبت شد و توسط ادمین بررسی می‌شود.")


class LMSAnswerReportView(APIView):
    """Report a lesson answer for moderation."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [LMSDiscussionThrottle]

    @extend_schema(operation_id="lms_answers_report", tags=[TAG_LMS_USER], request=DiscussionReportCreateSerializer, responses={201: DISCUSSION_REPORT_RESPONSE, 403: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, answer_id: int) -> CreatedResponse | ErrorResponse:
        """Report an answer."""
        answer = selectors.get_lesson_answer_by_id(answer_id=answer_id)
        if answer is None:
            return ErrorResponse(message="پاسخ یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            report = services.report_lesson_answer(answer=answer, reported_by=request.user, **serializer.validated_data)
        except LMSDiscussionAccessError as exc:
            return ErrorResponse(message=str(exc), status_code=status.HTTP_403_FORBIDDEN)
        log_action_async(user_id=request.user.pk, action=audit_actions.LMS_DISCUSSION_REPORTED, resource_type="lms_discussion_report", resource_id=str(report.pk), extra_data={"answer_id": answer.pk}, **extract_audit_metadata(request))
        return CreatedResponse(data=DiscussionReportSerializer(report).data, message="گزارش شما ثبت شد و توسط ادمین بررسی می‌شود.")


class LMSAdminQuestionModerationView(APIView):
    """Admin moderation for questions."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_questions_moderate", tags=[TAG_LMS_ADMIN], request=DiscussionModerationSerializer, responses={200: QUESTION_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def patch(self, request: Request, question_id: int) -> SuccessResponse | ErrorResponse:
        """Moderate one question."""
        question = selectors.get_lesson_question_by_id(question_id=question_id)
        if question is None:
            return ErrorResponse(message="سؤال یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = services.moderate_lesson_question(question=question, status=serializer.validated_data["status"], is_pinned=serializer.validated_data.get("is_pinned"))
        return SuccessResponse(data=LessonQuestionSerializer(question).data, message="وضعیت سؤال بروزرسانی شد.")


class LMSAdminAnswerModerationView(APIView):
    """Admin moderation for answers."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_answers_moderate", tags=[TAG_LMS_ADMIN], request=DiscussionModerationSerializer, responses={200: ANSWER_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def patch(self, request: Request, answer_id: int) -> SuccessResponse | ErrorResponse:
        """Moderate one answer."""
        answer = selectors.get_lesson_answer_by_id(answer_id=answer_id)
        if answer is None:
            return ErrorResponse(message="پاسخ یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        answer = services.moderate_lesson_answer(answer=answer, status=serializer.validated_data["status"], is_accepted=serializer.validated_data.get("is_accepted"))
        return SuccessResponse(data=LessonAnswerSerializer(answer).data, message="وضعیت پاسخ بروزرسانی شد.")


class LMSAdminDiscussionReportListView(APIView):
    """Admin list of discussion reports."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_discussion_reports_list", tags=[TAG_LMS_ADMIN], responses={200: DISCUSSION_REPORT_LIST_RESPONSE})
    def get(self, request: Request) -> Response:
        """Return paginated discussion reports."""
        queryset = selectors.get_admin_discussion_reports()
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = DiscussionReportSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class LMSAdminDiscussionReportReviewView(APIView):
    """Admin review for a discussion report."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_discussion_reports_review", tags=[TAG_LMS_ADMIN], request=DiscussionReportReviewSerializer, responses={200: DISCUSSION_REPORT_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def patch(self, request: Request, report_id: int) -> SuccessResponse | ErrorResponse:
        """Review one discussion report."""
        report = selectors.get_admin_discussion_report_by_id(report_id=report_id)
        if report is None:
            return ErrorResponse(message="گزارش یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = DiscussionReportReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.review_discussion_report(report=report, reviewed_by=request.user, status=serializer.validated_data["status"])
        return SuccessResponse(data=DiscussionReportSerializer(report).data, message="گزارش گفتگو بررسی شد.")


class LMSAdminCategoryListCreateView(APIView):
    """Admin list/create categories."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_categories_list", tags=[TAG_LMS_ADMIN], responses={200: CATEGORY_LIST_RESPONSE, 403: LMS_ERROR_RESPONSE})
    def get(self, request: Request) -> SuccessResponse:
        """Return all categories for admin."""
        queryset = selectors.get_admin_categories()
        filterset = LMSCategoryAdminFilter(request.query_params, queryset=queryset)
        if filterset.is_valid():
            queryset = filterset.qs
        return SuccessResponse(data=LMSCategorySerializer(queryset, many=True).data)

    @extend_schema(operation_id="lms_admin_categories_create", tags=[TAG_LMS_ADMIN], request=LMSCategoryCreateUpdateSerializer, responses={201: CATEGORY_RESPONSE, 400: LMS_ERROR_RESPONSE, 403: LMS_ERROR_RESPONSE})
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
        return CreatedResponse(data=LMSCategorySerializer(category).data, message="دسته‌بندی با موفقیت ساخته شد.")


class LMSAdminCategoryDetailView(APIView):
    """Admin retrieve/update/delete category."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_categories_retrieve", tags=[TAG_LMS_ADMIN], responses={200: CATEGORY_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Return one category for admin."""
        category = selectors.get_admin_category_by_id(category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=404)
        return SuccessResponse(data=LMSCategorySerializer(category).data)

    @extend_schema(operation_id="lms_admin_categories_update", tags=[TAG_LMS_ADMIN], request=LMSCategoryCreateUpdateSerializer, responses={200: CATEGORY_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def patch(self, request: Request, category_id: int) -> SuccessResponse | ErrorResponse:
        """Update category."""
        category = selectors.get_admin_category_by_id(category_id)
        if category is None:
            return ErrorResponse(message="دسته‌بندی یافت نشد.", status_code=404)
        serializer = LMSCategoryCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        category = services.update_category(category=category, **serializer.validated_data)
        return SuccessResponse(data=LMSCategorySerializer(category).data, message="دسته‌بندی بروزرسانی شد.")

    @extend_schema(operation_id="lms_admin_categories_delete", tags=[TAG_LMS_ADMIN], responses={200: build_success_response_serializer(name="LMSCategoryDeletedResponse"), 404: LMS_ERROR_RESPONSE})
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

    @extend_schema(operation_id="lms_admin_courses_list", tags=[TAG_LMS_ADMIN], responses={200: COURSE_LIST_RESPONSE})
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

    @extend_schema(operation_id="lms_admin_courses_create", tags=[TAG_LMS_ADMIN], request=CourseCreateUpdateSerializer, responses={201: COURSE_RESPONSE, 400: LMS_ERROR_RESPONSE})
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
        return CreatedResponse(data=CourseDetailSerializer(course).data, message="کلاس با موفقیت ساخته شد.")


class LMSAdminCourseDetailView(APIView):
    """Admin retrieve/update/delete course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_courses_retrieve", tags=[TAG_LMS_ADMIN], responses={200: COURSE_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Return one course for admin."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        return SuccessResponse(data=CourseDetailSerializer(course).data)

    @extend_schema(operation_id="lms_admin_courses_update", tags=[TAG_LMS_ADMIN], request=CourseCreateUpdateSerializer, responses={200: COURSE_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def patch(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Update course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        serializer = CourseCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        course = services.update_course(course=course, **serializer.validated_data)
        return SuccessResponse(data=CourseDetailSerializer(course).data, message="کلاس بروزرسانی شد.")

    @extend_schema(operation_id="lms_admin_courses_delete", tags=[TAG_LMS_ADMIN], responses={200: build_success_response_serializer(name="LMSCourseDeletedResponse"), 404: LMS_ERROR_RESPONSE})
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

    @extend_schema(operation_id="lms_admin_courses_publish", tags=[TAG_LMS_ADMIN], request=None, responses={200: COURSE_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Publish course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        course = services.publish_course(course=course)
        log_action_async(user_id=request.user.pk, action=audit_actions.LMS_COURSE_PUBLISHED, resource_type="lms_course", resource_id=str(course.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=CourseDetailSerializer(course).data, message="کلاس منتشر شد.")


class LMSAdminCourseArchiveView(APIView):
    """Admin archive course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_courses_archive", tags=[TAG_LMS_ADMIN], request=None, responses={200: COURSE_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Archive course."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        course = services.archive_course(course=course)
        log_action_async(user_id=request.user.pk, action=audit_actions.LMS_COURSE_ARCHIVED, resource_type="lms_course", resource_id=str(course.pk), **extract_audit_metadata(request))
        return SuccessResponse(data=CourseDetailSerializer(course).data, message="کلاس آرشیو شد.")


class LMSAdminLessonListCreateView(APIView):
    """Admin list/create lessons for a course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_lessons_list", tags=[TAG_LMS_ADMIN], responses={200: LESSON_LIST_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def get(self, request: Request, course_id: int) -> SuccessResponse | ErrorResponse:
        """Return all lessons for admin."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        lessons = selectors.get_course_lessons(course=course, public_only=False)
        return SuccessResponse(data=LessonSummarySerializer(lessons, many=True).data)

    @extend_schema(operation_id="lms_admin_lessons_create", tags=[TAG_LMS_ADMIN], request=LessonCreateUpdateSerializer, responses={201: LESSON_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def post(self, request: Request, course_id: int) -> CreatedResponse | ErrorResponse:
        """Create lesson."""
        course = selectors.get_admin_course_by_id(course_id)
        if course is None:
            return ErrorResponse(message="کلاس یافت نشد.", status_code=404)
        serializer = LessonCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lesson = services.create_lesson(course=course, **serializer.validated_data)
        log_action_async(user_id=request.user.pk, action=audit_actions.LMS_LESSON_CREATED, resource_type="lms_lesson", resource_id=str(lesson.pk), extra_data={"course_id": course.pk}, **extract_audit_metadata(request))
        return CreatedResponse(data=LessonSummarySerializer(lesson).data, message="جلسه ساخته شد.")


class LMSAdminLessonDetailView(APIView):
    """Admin update/delete lesson."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_lessons_update", tags=[TAG_LMS_ADMIN], request=LessonCreateUpdateSerializer, responses={200: LESSON_RESPONSE, 400: LMS_ERROR_RESPONSE, 404: LMS_ERROR_RESPONSE})
    def patch(self, request: Request, lesson_id: int) -> SuccessResponse | ErrorResponse:
        """Update lesson."""
        lesson = selectors.get_admin_lesson_by_id(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=404)
        serializer = LessonCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        lesson = services.update_lesson(lesson=lesson, **serializer.validated_data)
        return SuccessResponse(data=LessonSummarySerializer(lesson).data, message="جلسه بروزرسانی شد.")

    @extend_schema(operation_id="lms_admin_lessons_delete", tags=[TAG_LMS_ADMIN], responses={200: build_success_response_serializer(name="LMSLessonDeletedResponse"), 404: LMS_ERROR_RESPONSE})
    def delete(self, request: Request, lesson_id: int) -> DeletedResponse | ErrorResponse:
        """Soft-delete lesson."""
        lesson = selectors.get_admin_lesson_by_id(lesson_id=lesson_id)
        if lesson is None:
            return ErrorResponse(message="جلسه یافت نشد.", status_code=404)
        services.delete_lesson(lesson=lesson)
        return DeletedResponse(message="جلسه غیرفعال شد.")


class LMSAdminCourseReportView(APIView):
    """Admin detailed report for one course."""

    permission_classes = [IsLMSAdminUser]

    @extend_schema(operation_id="lms_admin_courses_report", tags=[TAG_LMS_ADMIN], responses={200: COURSE_REPORT_RESPONSE, 404: LMS_ERROR_RESPONSE})
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
            data=CourseReportSerializer({"course": course, "summary": summary, "enrollments": enrollments}).data,
            message="گزارش کلاس با موفقیت دریافت شد.",
        )
