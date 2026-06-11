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
    path("admin/questions/<int:question_id>/moderate/", views.LMSAdminQuestionModerationView.as_view(), name="admin-question-moderate"),
    path("admin/answers/<int:answer_id>/moderate/", views.LMSAdminAnswerModerationView.as_view(), name="admin-answer-moderate"),
    path("admin/discussion-reports/", views.LMSAdminDiscussionReportListView.as_view(), name="admin-discussion-report-list"),
    path("admin/discussion-reports/<int:report_id>/review/", views.LMSAdminDiscussionReportReviewView.as_view(), name="admin-discussion-report-review"),
]
