"""URL routing for Support Desk APIs."""

from django.urls import path

from apps.support_desk import views

app_name = "support_desk"

urlpatterns = [
    path("departments/", views.SupportDepartmentListView.as_view(), name="department-list"),
    path("categories/", views.SupportCategoryListView.as_view(), name="category-list"),
    path("ticket-types/", views.SupportTicketTypeListView.as_view(), name="ticket-type-list"),
    path("me/tickets/suggest/", views.SupportTicketSuggestView.as_view(), name="user-ticket-suggest"),
    path("me/tickets/", views.SupportUserTicketListCreateView.as_view(), name="user-ticket-list-create"),
    path("me/tickets/<str:ticket_number>/", views.SupportUserTicketDetailView.as_view(), name="user-ticket-detail"),
    path("me/tickets/<str:ticket_number>/submit/", views.SupportUserTicketSubmitView.as_view(), name="user-ticket-submit"),
    path("me/tickets/<str:ticket_number>/reply/", views.SupportUserTicketReplyView.as_view(), name="user-ticket-reply"),
    path("me/tickets/<str:ticket_number>/timeline/", views.SupportUserTicketTimelineView.as_view(), name="user-ticket-timeline"),
    path("me/tickets/<str:ticket_number>/attachments/", views.SupportUserTicketAttachmentView.as_view(), name="user-ticket-attachment"),
    path("me/tickets/<str:ticket_number>/reopen/", views.SupportUserTicketReopenView.as_view(), name="user-ticket-reopen"),
    path("me/tickets/<str:ticket_number>/satisfaction/", views.SupportUserTicketSatisfactionView.as_view(), name="user-ticket-satisfaction"),
    path("admin/departments/", views.SupportAdminDepartmentListCreateView.as_view(), name="admin-department-list-create"),
    path("admin/departments/<int:department_id>/", views.SupportAdminDepartmentDetailView.as_view(), name="admin-department-detail"),
    path("admin/categories/", views.SupportAdminCategoryListCreateView.as_view(), name="admin-category-list-create"),
    path("admin/categories/<int:category_id>/", views.SupportAdminCategoryDetailView.as_view(), name="admin-category-detail"),
    path("admin/ticket-types/", views.SupportAdminTicketTypeListCreateView.as_view(), name="admin-ticket-type-list-create"),
    path("admin/ticket-types/<int:ticket_type_id>/", views.SupportAdminTicketTypeDetailView.as_view(), name="admin-ticket-type-detail"),
    path("admin/business-calendars/", views.SupportAdminBusinessCalendarListCreateView.as_view(), name="admin-business-calendar-list-create"),
    path("admin/business-calendars/<int:calendar_id>/", views.SupportAdminBusinessCalendarDetailView.as_view(), name="admin-business-calendar-detail"),
    path("admin/holidays/", views.SupportAdminHolidayListCreateView.as_view(), name="admin-holiday-list-create"),
    path("admin/holidays/<int:holiday_id>/", views.SupportAdminHolidayDetailView.as_view(), name="admin-holiday-detail"),
    path("admin/sla-policies/", views.SupportAdminSLAPolicyListCreateView.as_view(), name="admin-sla-policy-list-create"),
    path("admin/sla-policies/<int:policy_id>/", views.SupportAdminSLAPolicyDetailView.as_view(), name="admin-sla-policy-detail"),
    path("admin/canned-responses/", views.SupportAdminCannedResponseListCreateView.as_view(), name="admin-canned-response-list-create"),
    path("admin/canned-responses/<int:canned_response_id>/", views.SupportAdminCannedResponseDetailView.as_view(), name="admin-canned-response-detail"),
    path("admin/canned-responses/<int:canned_response_id>/use/", views.SupportAdminCannedResponseUseView.as_view(), name="admin-canned-response-use"),
    path("admin/tickets/", views.SupportAdminTicketListView.as_view(), name="admin-ticket-list"),
    path("admin/tickets/<str:ticket_number>/", views.SupportAdminTicketDetailView.as_view(), name="admin-ticket-detail"),
    path("admin/tickets/<str:ticket_number>/reply/", views.SupportAdminTicketReplyView.as_view(), name="admin-ticket-reply"),
    path("admin/tickets/<str:ticket_number>/internal-note/", views.SupportAdminTicketInternalNoteView.as_view(), name="admin-ticket-internal-note"),
    path("admin/tickets/<str:ticket_number>/assign/", views.SupportAdminTicketAssignView.as_view(), name="admin-ticket-assign"),
    path("admin/tickets/<str:ticket_number>/assignment-recommendation/", views.SupportAdminTicketAssignmentRecommendationView.as_view(), name="admin-ticket-assignment-recommendation"),
    path("admin/tickets/<str:ticket_number>/auto-assign/", views.SupportAdminTicketAutoAssignView.as_view(), name="admin-ticket-auto-assign"),
    path("admin/tickets/<str:ticket_number>/status/", views.SupportAdminTicketStatusView.as_view(), name="admin-ticket-status"),
    path("admin/tickets/<str:ticket_number>/escalate/", views.SupportAdminTicketEscalateView.as_view(), name="admin-ticket-escalate"),
    path("admin/tickets/<str:ticket_number>/close/", views.SupportAdminTicketCloseView.as_view(), name="admin-ticket-close"),
    path("admin/duplicates/", views.SupportAdminDuplicateCandidateListView.as_view(), name="admin-duplicate-list"),
    path("admin/duplicates/<int:duplicate_id>/review/", views.SupportAdminDuplicateCandidateReviewView.as_view(), name="admin-duplicate-review"),
    path("admin/analytics/", views.SupportAdminAnalyticsView.as_view(), name="admin-analytics"),
    path("admin/export/tickets/", views.SupportAdminTicketExportView.as_view(), name="admin-export-tickets"),
    path("admin/export/messages/", views.SupportAdminMessageExportView.as_view(), name="admin-export-messages"),
    path("admin/export/sla/", views.SupportAdminSLAExportView.as_view(), name="admin-export-sla"),
    path("admin/export/csat/", views.SupportAdminCSATExportView.as_view(), name="admin-export-csat"),
]
