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
]
