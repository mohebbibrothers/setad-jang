"""URL routing دیوار مهربانی — namespace: kindness_wall.

عمومی: categories/listings/stories/stats؛ کاربر: اعلام آمادگی (upsert/پس‌گرفتن/فهرست من)؛
ادمین: CRUD دسته/آگهی + اکشن‌های چرخه حیات + تریاج اعلام + خروجی اکسل.
ساختار صریح و کم‌عمق نگه داشته شده تا فرانت بدون حدس مسیر کار کند.
"""

from django.urls import path

from apps.kindness_wall import views, views_admin

app_name = "kindness_wall"

urlpatterns = [
    # ── عمومی ──────────────────────────────────────────────
    path(
        "categories/",
        views.KindnessCategoryPublicListView.as_view(),
        name="category-list",
    ),
    path("listings/", views.KindnessListingPublicListView.as_view(), name="listing-list"),
    path(
        "listings/<str:slug>/",
        views.KindnessListingPublicDetailView.as_view(),
        name="listing-detail",
    ),
    path("stories/", views.KindnessStoryPublicListView.as_view(), name="story-list"),
    path("stats/", views.KindnessBoardStatsView.as_view(), name="stats"),
    # ── کاربر ──────────────────────────────────────────────
    path(
        "listings/<str:slug>/offer/",
        views.KindnessOfferCreateView.as_view(),
        name="offer-create",
    ),
    path(
        "offers/<int:offer_id>/withdraw/",
        views.KindnessOfferWithdrawView.as_view(),
        name="offer-withdraw",
    ),
    path("my-offers/", views.KindnessMyOffersView.as_view(), name="my-offers"),
    # ── ادمین ──────────────────────────────────────────────
    path(
        "admin/categories/",
        views_admin.KindnessAdminCategoryListView.as_view(),
        name="admin-category-list",
    ),
    path(
        "admin/categories/<int:category_id>/",
        views_admin.KindnessAdminCategoryDetailView.as_view(),
        name="admin-category-detail",
    ),
    path(
        "admin/listings/",
        views_admin.KindnessAdminListingListView.as_view(),
        name="admin-listing-list",
    ),
    path(
        "admin/listings/<int:listing_id>/",
        views_admin.KindnessAdminListingDetailView.as_view(),
        name="admin-listing-detail",
    ),
    path(
        "admin/listings/<int:listing_id>/<str:action>/",
        views_admin.KindnessAdminListingActionView.as_view(),
        name="admin-listing-action",
    ),
    path(
        "admin/offers/", views_admin.KindnessAdminOfferListView.as_view(), name="admin-offer-list"
    ),
    path(
        "admin/offers/<int:offer_id>/review/",
        views_admin.KindnessAdminOfferReviewView.as_view(),
        name="admin-offer-review",
    ),
    path(
        "admin/export/listings/",
        views_admin.KindnessAdminListingsExportView.as_view(),
        name="admin-export-listings",
    ),
    path(
        "admin/export/offers/",
        views_admin.KindnessAdminOffersExportView.as_view(),
        name="admin-export-offers",
    ),
]
