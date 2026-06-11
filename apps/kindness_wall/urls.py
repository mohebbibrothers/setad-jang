"""URL routing for Kindness Wall."""

from django.urls import path

from apps.kindness_wall import views

app_name = "kindness_wall"

urlpatterns = [
    path("categories/", views.KindnessCategoryPublicListView.as_view(), name="category-list"),
    path("listings/", views.KindnessListingPublicListView.as_view(), name="listing-list"),
    path("listings/<str:slug>/", views.KindnessListingPublicDetailView.as_view(), name="listing-detail"),
    path("listings/<str:slug>/matches/", views.KindnessListingPublicMatchesView.as_view(), name="listing-matches"),
    path("listings/<str:slug>/reveal-contact/", views.KindnessContactRevealView.as_view(), name="listing-reveal-contact"),
    path("listings/<str:slug>/report/", views.KindnessListingReportCreateView.as_view(), name="listing-report"),
    path("listings/<str:slug>/bookmark/", views.KindnessBookmarkView.as_view(), name="listing-bookmark"),
    path("me/listings/", views.KindnessUserListingListCreateView.as_view(), name="user-listing-list-create"),
    path("me/listings/<int:listing_id>/", views.KindnessUserListingDetailView.as_view(), name="user-listing-detail"),
    path("me/listings/<int:listing_id>/submit/", views.KindnessUserListingSubmitView.as_view(), name="user-listing-submit"),
    path("me/listings/<int:listing_id>/renew/", views.KindnessUserListingRenewView.as_view(), name="user-listing-renew"),
    path("me/matches/", views.KindnessUserMatchListView.as_view(), name="user-match-list"),
    path("me/matches/<int:match_id>/dismiss/", views.KindnessMatchDismissView.as_view(), name="user-match-dismiss"),
    path("me/matches/<int:match_id>/contacted/", views.KindnessMatchContactedView.as_view(), name="user-match-contacted"),
    path("admin/listings/", views.KindnessAdminListingListView.as_view(), name="admin-listing-list"),
    path("admin/listings/<int:listing_id>/", views.KindnessAdminListingDetailView.as_view(), name="admin-listing-detail"),
    path("admin/listings/<int:listing_id>/approve/", views.KindnessAdminListingApproveView.as_view(), name="admin-listing-approve"),
    path("admin/listings/<int:listing_id>/reject/", views.KindnessAdminListingRejectView.as_view(), name="admin-listing-reject"),
    path("admin/listings/<int:listing_id>/suspend/", views.KindnessAdminListingSuspendView.as_view(), name="admin-listing-suspend"),
    path("admin/listings/<int:listing_id>/restore/", views.KindnessAdminListingRestoreView.as_view(), name="admin-listing-restore"),
    path("admin/reports/", views.KindnessAdminReportListView.as_view(), name="admin-report-list"),
    path("admin/reports/<int:report_id>/review/", views.KindnessAdminReportReviewView.as_view(), name="admin-report-review"),
    path("admin/analytics/", views.KindnessAdminAnalyticsView.as_view(), name="admin-analytics"),
]
