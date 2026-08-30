"""مشترکات views — constants/helpers که گروه‌های دامنه‌ای import می‌کنند.

با ابزار split_views در فاز ۱۱ از views.py جدا شد؛ منطق دست‌نخورده است(برشِ verbatim). facade در views.py همه را دوباره export می‌کند تا مسیرهایimport بیرونی (urls/tests) تغییر نکنند.
"""

from __future__ import annotations

from apps.core.schemas import (
    build_error_response_serializer,
    build_paginated_success_response_serializer,
    build_success_response_serializer,
)
from apps.lms.serializers import (
    CertificateSerializer,
    CertificateVerifySerializer,
    CourseAnalyticsSerializer,
    CourseDetailSerializer,
    CourseLeaderboardItemSerializer,
    CourseReportSerializer,
    CourseSummarySerializer,
    DiscussionReportSerializer,
    EnrollmentDetailSerializer,
    EnrollmentSerializer,
    LearningActivityStatementSerializer,
    LearningRecommendationItemSerializer,
    LearningRecommendationOverviewSerializer,
    LessonAnswerSerializer,
    LessonMediaAccessSerializer,
    LessonProgressSerializer,
    LessonQuestionSerializer,
    LessonSummarySerializer,
    LessonVideoProcessingJobSerializer,
    LMSCategorySerializer,
    LMSUserSkillSerializer,
    QuizAdminSerializer,
    QuizAttemptDetailSerializer,
    QuizOptionAdminSerializer,
    QuizPublicSerializer,
    QuizQuestionAdminSerializer,
    QuizUnlockSerializer,
)

TAG_LMS_PUBLIC = "آموزش — عمومی"
TAG_LMS_USER = "آموزش — کاربر"
TAG_LMS_ADMIN = "آموزش — مدیریت"
LMS_ERROR_RESPONSE = build_error_response_serializer(name="LMSErrorResponse")
CATEGORY_RESPONSE = build_success_response_serializer(
    name="LMSCategoryResponse", data_serializer=LMSCategorySerializer
)
CATEGORY_LIST_RESPONSE = build_success_response_serializer(
    name="LMSCategoryListResponse", data_serializer=LMSCategorySerializer, many=True
)
COURSE_RESPONSE = build_success_response_serializer(
    name="LMSCourseResponse", data_serializer=CourseDetailSerializer
)
COURSE_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="LMSCourseListResponse", item_serializer=CourseSummarySerializer
)
LESSON_RESPONSE = build_success_response_serializer(
    name="LMSLessonResponse", data_serializer=LessonSummarySerializer
)
LESSON_MEDIA_RESPONSE = build_success_response_serializer(
    name="LMSLessonMediaAccessResponse", data_serializer=LessonMediaAccessSerializer
)
LESSON_LIST_RESPONSE = build_success_response_serializer(
    name="LMSLessonListResponse", data_serializer=LessonSummarySerializer, many=True
)
ENROLLMENT_RESPONSE = build_success_response_serializer(
    name="LMSEnrollmentResponse", data_serializer=EnrollmentSerializer
)
ENROLLMENT_DETAIL_RESPONSE = build_success_response_serializer(
    name="LMSEnrollmentDetailResponse", data_serializer=EnrollmentDetailSerializer
)
ENROLLMENT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="LMSEnrollmentListResponse", item_serializer=EnrollmentSerializer
)
LESSON_PROGRESS_RESPONSE = build_success_response_serializer(
    name="LMSLessonProgressResponse", data_serializer=LessonProgressSerializer
)
QUESTION_RESPONSE = build_success_response_serializer(
    name="LMSLessonQuestionResponse", data_serializer=LessonQuestionSerializer
)
QUESTION_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="LMSLessonQuestionListResponse", item_serializer=LessonQuestionSerializer
)
ANSWER_RESPONSE = build_success_response_serializer(
    name="LMSLessonAnswerResponse", data_serializer=LessonAnswerSerializer
)
DISCUSSION_REPORT_RESPONSE = build_success_response_serializer(
    name="LMSDiscussionReportResponse", data_serializer=DiscussionReportSerializer
)
DISCUSSION_REPORT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="LMSDiscussionReportListResponse", item_serializer=DiscussionReportSerializer
)
QUIZ_PUBLIC_RESPONSE = build_success_response_serializer(
    name="LMSQuizPublicResponse", data_serializer=QuizPublicSerializer
)
QUIZ_ADMIN_RESPONSE = build_success_response_serializer(
    name="LMSQuizAdminResponse", data_serializer=QuizAdminSerializer
)
QUIZ_QUESTION_RESPONSE = build_success_response_serializer(
    name="LMSQuizQuestionResponse", data_serializer=QuizQuestionAdminSerializer
)
QUIZ_OPTION_RESPONSE = build_success_response_serializer(
    name="LMSQuizOptionResponse", data_serializer=QuizOptionAdminSerializer
)
QUIZ_ATTEMPT_RESPONSE = build_success_response_serializer(
    name="LMSQuizAttemptResponse", data_serializer=QuizAttemptDetailSerializer
)
QUIZ_UNLOCK_RESPONSE = build_success_response_serializer(
    name="LMSQuizUnlockResponse", data_serializer=QuizUnlockSerializer
)
CERTIFICATE_RESPONSE = build_success_response_serializer(
    name="LMSCertificateResponse", data_serializer=CertificateSerializer
)
CERTIFICATE_VERIFY_RESPONSE = build_success_response_serializer(
    name="LMSCertificateVerifyResponse", data_serializer=CertificateVerifySerializer
)
CERTIFICATE_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="LMSCertificateListResponse", item_serializer=CertificateSerializer
)
SKILL_LIST_RESPONSE = build_success_response_serializer(
    name="LMSSkillListResponse", data_serializer=LMSUserSkillSerializer, many=True
)
COURSE_REPORT_RESPONSE = build_success_response_serializer(
    name="LMSCourseReportResponse", data_serializer=CourseReportSerializer
)
COURSE_ANALYTICS_RESPONSE = build_success_response_serializer(
    name="LMSCourseAnalyticsResponse", data_serializer=CourseAnalyticsSerializer
)
COURSE_LEADERBOARD_RESPONSE = build_success_response_serializer(
    name="LMSCourseLeaderboardResponse", data_serializer=CourseLeaderboardItemSerializer, many=True
)
VIDEO_PROCESSING_JOB_RESPONSE = build_success_response_serializer(
    name="LMSVideoProcessingJobResponse", data_serializer=LessonVideoProcessingJobSerializer
)
LEARNING_RECOMMENDATION_RESPONSE = build_success_response_serializer(
    name="LMSLearningRecommendationResponse",
    data_serializer=LearningRecommendationItemSerializer,
    many=True,
)
LEARNING_RECOMMENDATION_OVERVIEW_RESPONSE = build_success_response_serializer(
    name="LMSLearningRecommendationOverviewResponse",
    data_serializer=LearningRecommendationOverviewSerializer,
)
LEARNING_STATEMENT_LIST_RESPONSE = build_paginated_success_response_serializer(
    name="LMSLearningStatementListResponse", item_serializer=LearningActivityStatementSerializer
)
