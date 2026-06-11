"""URL routing for the LMS application."""

from django.urls import path

from apps.lms import views

app_name = "lms"

urlpatterns = [
    path("categories/", views.LMSCategoryPublicListView.as_view(), name="category-list"),
    path("categories/<str:slug>/", views.LMSCategoryPublicDetailView.as_view(), name="category-detail"),
    path("courses/", views.LMSCoursePublicListView.as_view(), name="course-list"),
    path("courses/<str:slug>/", views.LMSCoursePublicDetailView.as_view(), name="course-detail"),
    path("courses/<str:slug>/lessons/", views.LMSCourseLessonsPublicView.as_view(), name="course-lessons"),
    path("courses/<str:slug>/lessons/<str:lesson_slug>/", views.LMSLessonPublicDetailView.as_view(), name="lesson-detail"),
    path("courses/<str:slug>/enroll/", views.LMSUserEnrollView.as_view(), name="course-enroll"),
    path("courses/<str:slug>/quiz/", views.LMSCourseQuizPublicView.as_view(), name="course-quiz"),
    path("courses/<str:slug>/quiz/start/", views.LMSQuizAttemptStartView.as_view(), name="quiz-attempt-start"),
    path("quiz/attempts/<int:attempt_id>/", views.LMSQuizAttemptDetailView.as_view(), name="quiz-attempt-detail"),
    path("quiz/attempts/<int:attempt_id>/submit/", views.LMSQuizAttemptSubmitView.as_view(), name="quiz-attempt-submit"),
    path("certificates/verify/<str:verification_slug>/", views.LMSCertificateVerifyView.as_view(), name="certificate-verify"),
    path("me/certificates/", views.LMSUserCertificateListView.as_view(), name="user-certificate-list"),
    path("me/certificates/<int:certificate_id>/", views.LMSUserCertificateDetailView.as_view(), name="user-certificate-detail"),
    path("me/enrollments/", views.LMSUserEnrollmentListView.as_view(), name="user-enrollment-list"),
    path("me/enrollments/<int:enrollment_id>/", views.LMSUserEnrollmentDetailView.as_view(), name="user-enrollment-detail"),
    path("lessons/<int:lesson_id>/progress/", views.LMSLessonProgressUpdateView.as_view(), name="lesson-progress-update"),
    path("lessons/<int:lesson_id>/questions/", views.LMSLessonQuestionListCreateView.as_view(), name="lesson-question-list-create"),
    path("questions/<int:question_id>/answers/", views.LMSQuestionAnswerCreateView.as_view(), name="question-answer-create"),
    path("questions/<int:question_id>/answers/<int:answer_id>/accept/", views.LMSQuestionAcceptAnswerView.as_view(), name="question-answer-accept"),
    path("questions/<int:question_id>/report/", views.LMSQuestionReportView.as_view(), name="question-report"),
    path("answers/<int:answer_id>/report/", views.LMSAnswerReportView.as_view(), name="answer-report"),
    path("me/skills/", views.LMSUserSkillListView.as_view(), name="user-skill-list"),
    path("admin/categories/", views.LMSAdminCategoryListCreateView.as_view(), name="admin-category-list-create"),
    path("admin/categories/<int:category_id>/", views.LMSAdminCategoryDetailView.as_view(), name="admin-category-detail"),
    path("admin/courses/", views.LMSAdminCourseListCreateView.as_view(), name="admin-course-list-create"),
    path("admin/courses/<int:course_id>/", views.LMSAdminCourseDetailView.as_view(), name="admin-course-detail"),
    path("admin/courses/<int:course_id>/publish/", views.LMSAdminCoursePublishView.as_view(), name="admin-course-publish"),
    path("admin/courses/<int:course_id>/archive/", views.LMSAdminCourseArchiveView.as_view(), name="admin-course-archive"),
    path("admin/courses/<int:course_id>/lessons/", views.LMSAdminLessonListCreateView.as_view(), name="admin-lesson-list-create"),
    path("admin/lessons/<int:lesson_id>/", views.LMSAdminLessonDetailView.as_view(), name="admin-lesson-detail"),
    path("admin/courses/<int:course_id>/report/", views.LMSAdminCourseReportView.as_view(), name="admin-course-report"),
    path("admin/courses/<int:course_id>/quiz/", views.LMSAdminQuizDetailCreateView.as_view(), name="admin-quiz-detail-create"),
    path("admin/courses/<int:course_id>/quiz/publish/", views.LMSAdminQuizPublishView.as_view(), name="admin-quiz-publish"),
    path("admin/courses/<int:course_id>/quiz/questions/", views.LMSAdminQuizQuestionCreateView.as_view(), name="admin-quiz-question-create"),
    path("admin/quiz/questions/<int:question_id>/options/", views.LMSAdminQuizOptionCreateView.as_view(), name="admin-quiz-option-create"),
    path("admin/courses/<int:course_id>/quiz/unlock/", views.LMSAdminQuizUnlockView.as_view(), name="admin-quiz-unlock"),
    path("admin/certificates/<int:certificate_id>/revoke/", views.LMSAdminCertificateRevokeView.as_view(), name="admin-certificate-revoke"),
    path("admin/questions/<int:question_id>/moderate/", views.LMSAdminQuestionModerationView.as_view(), name="admin-question-moderate"),
    path("admin/answers/<int:answer_id>/moderate/", views.LMSAdminAnswerModerationView.as_view(), name="admin-answer-moderate"),
    path("admin/discussion-reports/", views.LMSAdminDiscussionReportListView.as_view(), name="admin-discussion-report-list"),
    path("admin/discussion-reports/<int:report_id>/review/", views.LMSAdminDiscussionReportReviewView.as_view(), name="admin-discussion-report-review"),
]
