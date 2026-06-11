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
]
