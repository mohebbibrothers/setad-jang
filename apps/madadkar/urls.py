"""
URL routing اپ مددکار.

ساختار namespace‌بندی:
- /sponsors/                              — public: مددکاران
- /campaigns/                             — public: حرکت‌ها
- /campaigns/{slug}/participate/          — user: شروع مشارکت
- /payment/verify/                        — user: callback تأیید پرداخت
- /me/participations/                     — user: لیست مشارکت‌های من
- /me/participations/{id}/                — user: جزئیات یک مشارکت
- /admin/sponsors/                        — admin: مددکاران
- /admin/campaigns/                       — admin: حرکت‌ها
- /admin/campaigns/{id}/publish/          — admin: انتشار
- /admin/campaigns/{id}/close/            — admin: بستن
- /admin/campaigns/{id}/images/           — admin: گالری
- /admin/campaigns/{id}/participants/     — admin: مشارکت‌کنندگان (analytics)
- /admin/campaigns/{id}/leaderboard/      — admin: top contributors
- /admin/campaigns/{id}/analytics/        — admin: آمار تجمیعی
- /admin/campaigns/{id}/export/           — admin: خروجی Excel
- /admin/payments/                        — admin: لیست تمام پرداخت‌ها

اصول طراحی:
- public endpointها از slug استفاده می‌کنند (URL خوانا و SEO-friendly).
- admin endpointها از id استفاده می‌کنند (مستقل از slug که ممکن است عوض شود).
- user endpointهای personal از /me/ شروع می‌شوند.
- nested resourceها زیر parent قرار دارند.
- از <str:slug> به جای <slug:slug> استفاده می‌شود چون slugها allow_unicode=True
  هستند و باید کاراکترهای فارسی را در URL پشتیبانی کنند.
- ترتیب URLها مهم است: مسیرهای خاص‌تر (مثل /campaigns/{slug}/participate/)
  باید قبل از مسیرهای generic (مثل /campaigns/{slug}/) قرار بگیرند.
"""

from django.urls import path

from .views import (
    MadadkarAdminAdjustmentActionView,
    MadadkarAdminAdjustmentListCreateView,
    MadadkarAdminCampaignAnalyticsView,
    MadadkarAdminCampaignCloseView,
    MadadkarAdminCampaignDetailView,
    MadadkarAdminCampaignDisbursableSummaryView,
    MadadkarAdminCampaignExportView,
    MadadkarAdminCampaignFinancialControlView,
    MadadkarAdminCampaignImageDeleteView,
    MadadkarAdminCampaignImageListCreateView,
    MadadkarAdminCampaignIntelligenceView,
    MadadkarAdminCampaignLeaderboardView,
    MadadkarAdminCampaignListCreateView,
    MadadkarAdminCampaignParticipantsListView,
    MadadkarAdminCampaignPublishView,
    MadadkarAdminDisbursementActionView,
    MadadkarAdminDisbursementDetailView,
    MadadkarAdminDisbursementListCreateView,
    MadadkarAdminIntelligenceOverviewView,
    MadadkarAdminPaymentListView,
    MadadkarAdminReceiptResendView,
    MadadkarAdminReconciliationBatchDetailView,
    MadadkarAdminReconciliationBatchListView,
    MadadkarAdminReconciliationDiscrepancyExportView,
    MadadkarAdminReconciliationImportView,
    MadadkarAdminReconciliationItemListView,
    MadadkarAdminRefundActionView,
    MadadkarAdminRefundListCreateView,
    MadadkarAdminRiskSignalListView,
    MadadkarAdminRiskSignalReviewView,
    MadadkarAdminSponsorDetailView,
    MadadkarAdminSponsorListCreateView,
    MadadkarPaymentVerifyView,
    MadadkarPublicCampaignDetailView,
    MadadkarPublicCampaignListView,
    MadadkarPublicCampaignTransparencyView,
    MadadkarPublicReceiptVerifyView,
    MadadkarPublicSponsorDetailView,
    MadadkarPublicSponsorListView,
    MadadkarUserMyParticipationDetailView,
    MadadkarUserMyParticipationsListView,
    MadadkarUserParticipateView,
    MadadkarUserReceiptDetailView,
    MadadkarUserReceiptListView,
)

app_name = "madadkar"

urlpatterns = [
    # ====================================================
    # Public — Sponsors
    # ====================================================
    path(
        "sponsors/",
        MadadkarPublicSponsorListView.as_view(),
        name="public-sponsor-list",
    ),
    path(
        "sponsors/<str:slug>/",
        MadadkarPublicSponsorDetailView.as_view(),
        name="public-sponsor-detail",
    ),

    # ====================================================
    # User — Participation Initiate (روی campaign)
    # ====================================================
    # ⚠️ این path باید قبل از /campaigns/<slug>/ بیاید
    # چون <str:slug> generic است و <slug>/participate/ خاص‌تر است.
    path(
        "campaigns/<str:slug>/participate/",
        MadadkarUserParticipateView.as_view(),
        name="user-participate",
    ),

    # ====================================================
    # Public — Campaigns
    # ====================================================
    path(
        "campaigns/",
        MadadkarPublicCampaignListView.as_view(),
        name="public-campaign-list",
    ),
    path(
        "campaigns/<str:slug>/transparency/",
        MadadkarPublicCampaignTransparencyView.as_view(),
        name="public-campaign-transparency",
    ),
    path(
        "campaigns/<str:slug>/",
        MadadkarPublicCampaignDetailView.as_view(),
        name="public-campaign-detail",
    ),

    # ====================================================
    # User — Payment Verify Callback (از سمت درگاه)
    # ====================================================
    path(
        "payment/verify/",
        MadadkarPaymentVerifyView.as_view(),
        name="payment-verify",
    ),
    path(
        "receipts/verify/",
        MadadkarPublicReceiptVerifyView.as_view(),
        name="public-receipt-verify",
    ),

    # ====================================================
    # User — My Participations
    # ====================================================
    path(
        "me/participations/",
        MadadkarUserMyParticipationsListView.as_view(),
        name="user-my-participations-list",
    ),
    path(
        "me/participations/<int:participation_id>/",
        MadadkarUserMyParticipationDetailView.as_view(),
        name="user-my-participation-detail",
    ),
    path(
        "me/receipts/",
        MadadkarUserReceiptListView.as_view(),
        name="user-receipt-list",
    ),
    path(
        "me/receipts/<int:receipt_id>/",
        MadadkarUserReceiptDetailView.as_view(),
        name="user-receipt-detail",
    ),

    # ====================================================
    # Admin — Sponsors CRUD
    # ====================================================
    path(
        "admin/sponsors/",
        MadadkarAdminSponsorListCreateView.as_view(),
        name="admin-sponsor-list-create",
    ),
    path(
        "admin/sponsors/<int:sponsor_id>/",
        MadadkarAdminSponsorDetailView.as_view(),
        name="admin-sponsor-detail",
    ),

    # ====================================================
    # Admin — Campaigns CRUD
    # ====================================================
    path(
        "admin/campaigns/",
        MadadkarAdminCampaignListCreateView.as_view(),
        name="admin-campaign-list-create",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/",
        MadadkarAdminCampaignDetailView.as_view(),
        name="admin-campaign-detail",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/publish/",
        MadadkarAdminCampaignPublishView.as_view(),
        name="admin-campaign-publish",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/close/",
        MadadkarAdminCampaignCloseView.as_view(),
        name="admin-campaign-close",
    ),

    # ====================================================
    # Admin — Campaign Gallery
    # ====================================================
    path(
        "admin/campaigns/<int:campaign_id>/images/",
        MadadkarAdminCampaignImageListCreateView.as_view(),
        name="admin-campaign-image-list-create",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/images/<int:image_id>/",
        MadadkarAdminCampaignImageDeleteView.as_view(),
        name="admin-campaign-image-delete",
    ),

    # ====================================================
    # Admin — Campaign Analytics & Reports
    # ====================================================
    path(
        "admin/campaigns/<int:campaign_id>/participants/",
        MadadkarAdminCampaignParticipantsListView.as_view(),
        name="admin-campaign-participants",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/leaderboard/",
        MadadkarAdminCampaignLeaderboardView.as_view(),
        name="admin-campaign-leaderboard",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/analytics/",
        MadadkarAdminCampaignAnalyticsView.as_view(),
        name="admin-campaign-analytics",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/export/",
        MadadkarAdminCampaignExportView.as_view(),
        name="admin-campaign-export",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/financial-control/",
        MadadkarAdminCampaignFinancialControlView.as_view(),
        name="admin-campaign-financial-control",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/intelligence/",
        MadadkarAdminCampaignIntelligenceView.as_view(),
        name="admin-campaign-intelligence",
    ),
    path(
        "admin/campaigns/<int:campaign_id>/disbursable/",
        MadadkarAdminCampaignDisbursableSummaryView.as_view(),
        name="admin-campaign-disbursable",
    ),
    path(
        "admin/intelligence/overview/",
        MadadkarAdminIntelligenceOverviewView.as_view(),
        name="admin-intelligence-overview",
    ),

    # ====================================================
    # Admin — Refunds / Adjustments
    # ====================================================
    path(
        "admin/refunds/",
        MadadkarAdminRefundListCreateView.as_view(),
        name="admin-refund-list-create",
    ),
    path(
        "admin/refunds/<int:refund_id>/<str:action>/",
        MadadkarAdminRefundActionView.as_view(),
        name="admin-refund-action",
    ),
    path(
        "admin/adjustments/",
        MadadkarAdminAdjustmentListCreateView.as_view(),
        name="admin-adjustment-list-create",
    ),
    path(
        "admin/adjustments/<int:adjustment_id>/<str:action>/",
        MadadkarAdminAdjustmentActionView.as_view(),
        name="admin-adjustment-action",
    ),
    path(
        "admin/risk-signals/",
        MadadkarAdminRiskSignalListView.as_view(),
        name="admin-risk-signal-list",
    ),
    path(
        "admin/risk-signals/<int:signal_id>/review/",
        MadadkarAdminRiskSignalReviewView.as_view(),
        name="admin-risk-signal-review",
    ),
    path(
        "admin/receipts/<int:receipt_id>/resend/",
        MadadkarAdminReceiptResendView.as_view(),
        name="admin-receipt-resend",
    ),

    # ====================================================
    # Admin — Reconciliation
    # ====================================================
    path(
        "admin/disbursements/",
        MadadkarAdminDisbursementListCreateView.as_view(),
        name="admin-disbursement-list-create",
    ),
    path(
        "admin/disbursements/<int:disbursement_id>/",
        MadadkarAdminDisbursementDetailView.as_view(),
        name="admin-disbursement-detail",
    ),
    path(
        "admin/disbursements/<int:disbursement_id>/<str:action>/",
        MadadkarAdminDisbursementActionView.as_view(),
        name="admin-disbursement-action",
    ),
    path(
        "admin/reconciliation/import/",
        MadadkarAdminReconciliationImportView.as_view(),
        name="admin-reconciliation-import",
    ),
    path(
        "admin/reconciliation/batches/",
        MadadkarAdminReconciliationBatchListView.as_view(),
        name="admin-reconciliation-batch-list",
    ),
    path(
        "admin/reconciliation/batches/<int:batch_id>/",
        MadadkarAdminReconciliationBatchDetailView.as_view(),
        name="admin-reconciliation-batch-detail",
    ),
    path(
        "admin/reconciliation/batches/<int:batch_id>/items/",
        MadadkarAdminReconciliationItemListView.as_view(),
        name="admin-reconciliation-item-list",
    ),
    path(
        "admin/reconciliation/batches/<int:batch_id>/export/",
        MadadkarAdminReconciliationDiscrepancyExportView.as_view(),
        name="admin-reconciliation-discrepancy-export",
    ),

    # ====================================================
    # Admin — All Payments
    # ====================================================
    path(
        "admin/payments/",
        MadadkarAdminPaymentListView.as_view(),
        name="admin-payments-list",
    ),
]
