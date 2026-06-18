"""
URL routing اپ R4J — Reward for Justice.

ساختار namespace‌بندی:
- /criminals/             — public endpoints
- /criminals/{id}/reports/ — user report submit
- /me/reports/            — user: my reports
- /me/bounties/           — user: my bounties
- /criminals/{id}/bounty/ — user: set/update bounty
- /admin/criminals/       — admin: criminal CRUD
- /admin/reports/         — admin: report management
- /admin/bounties/        — admin: bounty management

اصول طراحی:
- public endpointها بدون پیشوند admin/ هستند.
- user endpointهای personal از /me/ شروع می‌شوند.
- user endpointهای مربوط به criminal از /criminals/{id}/ شروع می‌شوند.
- تمام admin endpoints پشت /admin/ قرار دارند.
- slug یا id برای public criminal detail هر دو پشتیبانی می‌شود (str lookup).
"""

from django.urls import path

from .views import (
    R4JAdminAliasDeleteView,
    R4JAdminAliasListCreateView,
    R4JAdminAttachmentDetailView,
    R4JAdminAttachmentListCreateView,
    R4JAdminBountyCancelApproveView,
    R4JAdminBountyCancelRejectView,
    R4JAdminBountyDetailView,
    R4JAdminBountyListView,
    R4JAdminCaseAssignView,
    R4JAdminCaseCloseView,
    R4JAdminCaseCreateFromReportView,
    R4JAdminCaseDetailView,
    R4JAdminCaseEscalateView,
    R4JAdminCaseEvidenceRequestView,
    R4JAdminCaseListView,
    R4JAdminCaseOperationsOverviewView,
    R4JAdminCasePriorityView,
    R4JAdminCaseRejectView,
    R4JAdminCaseReopenView,
    R4JAdminCaseResolveView,
    R4JAdminCaseTimelineView,
    R4JAdminCaseTriageView,
    R4JAdminCriminalDetailView,
    R4JAdminCriminalListCreateView,
    R4JAdminCriminalPublishView,
    R4JAdminCriminalUnpublishView,
    R4JAdminEvidenceCustodyListView,
    R4JAdminEvidenceCustodyReviewView,
    R4JAdminFieldVisibilityListUpsertView,
    R4JAdminPhoneDetailView,
    R4JAdminPhoneListCreateView,
    R4JAdminPhotoDetailView,
    R4JAdminPhotoListCreateView,
    R4JAdminPhotoSetPrimaryView,
    R4JAdminReportCancelApproveView,
    R4JAdminReportCancelRejectView,
    R4JAdminReportDetailView,
    R4JAdminReportListView,
    R4JAdminReportReviewView,
    R4JAdminSocialDetailView,
    R4JAdminSocialListCreateView,
    R4JPublicCriminalDetailView,
    R4JPublicCriminalListView,
    R4JUserBountyCancelView,
    R4JUserBountySetView,
    R4JUserMyBountiesListView,
    R4JUserMyReportDetailView,
    R4JUserMyReportsListView,
    R4JUserReportCancelView,
    R4JUserReportSubmitView,
)

app_name = "r4j"

urlpatterns = [
    # ====================================================
    # Public — Criminals
    # ====================================================
    path(
        "criminals/",
        R4JPublicCriminalListView.as_view(),
        name="public-criminal-list",
    ),
    path(
        "criminals/<str:lookup>/",
        R4JPublicCriminalDetailView.as_view(),
        name="public-criminal-detail",
    ),

    # ====================================================
    # User — Report Submit (روی criminal)
    # ====================================================
    path(
        "criminals/<int:criminal_id>/reports/",
        R4JUserReportSubmitView.as_view(),
        name="user-report-submit",
    ),

    # ====================================================
    # User — Bounty Set (روی criminal)
    # ====================================================
    path(
        "criminals/<int:criminal_id>/bounty/",
        R4JUserBountySetView.as_view(),
        name="user-bounty-set",
    ),

    # ====================================================
    # User — My Reports
    # ====================================================
    path(
        "me/reports/",
        R4JUserMyReportsListView.as_view(),
        name="user-my-reports-list",
    ),
    path(
        "me/reports/<int:report_id>/",
        R4JUserMyReportDetailView.as_view(),
        name="user-my-report-detail",
    ),
    path(
        "me/reports/<int:report_id>/cancel/",
        R4JUserReportCancelView.as_view(),
        name="user-report-cancel",
    ),

    # ====================================================
    # User — My Bounties
    # ====================================================
    path(
        "me/bounties/",
        R4JUserMyBountiesListView.as_view(),
        name="user-my-bounties-list",
    ),
    path(
        "me/bounties/<int:bounty_id>/cancel/",
        R4JUserBountyCancelView.as_view(),
        name="user-bounty-cancel",
    ),

    # ====================================================
    # Admin — Investigation Cases
    # ====================================================
    path(
        "admin/cases/",
        R4JAdminCaseListView.as_view(),
        name="admin-case-list",
    ),
    path(
        "admin/reports/<int:report_id>/create-case/",
        R4JAdminCaseCreateFromReportView.as_view(),
        name="admin-case-create-from-report",
    ),
    path(
        "admin/cases/<str:case_number>/",
        R4JAdminCaseDetailView.as_view(),
        name="admin-case-detail",
    ),
    path(
        "admin/cases/<str:case_number>/triage/",
        R4JAdminCaseTriageView.as_view(),
        name="admin-case-triage",
    ),
    path(
        "admin/cases/<str:case_number>/assign/",
        R4JAdminCaseAssignView.as_view(),
        name="admin-case-assign",
    ),
    path(
        "admin/cases/<str:case_number>/priority/",
        R4JAdminCasePriorityView.as_view(),
        name="admin-case-priority",
    ),
    path(
        "admin/cases/<str:case_number>/request-evidence/",
        R4JAdminCaseEvidenceRequestView.as_view(),
        name="admin-case-request-evidence",
    ),
    path(
        "admin/cases/<str:case_number>/escalate/",
        R4JAdminCaseEscalateView.as_view(),
        name="admin-case-escalate",
    ),
    path(
        "admin/cases/<str:case_number>/resolve/",
        R4JAdminCaseResolveView.as_view(),
        name="admin-case-resolve",
    ),
    path(
        "admin/cases/<str:case_number>/reject/",
        R4JAdminCaseRejectView.as_view(),
        name="admin-case-reject",
    ),
    path(
        "admin/cases/<str:case_number>/close/",
        R4JAdminCaseCloseView.as_view(),
        name="admin-case-close",
    ),
    path(
        "admin/cases/<str:case_number>/reopen/",
        R4JAdminCaseReopenView.as_view(),
        name="admin-case-reopen",
    ),
    path(
        "admin/cases/<str:case_number>/timeline/",
        R4JAdminCaseTimelineView.as_view(),
        name="admin-case-timeline",
    ),
    path(
        "admin/operations/overview/",
        R4JAdminCaseOperationsOverviewView.as_view(),
        name="admin-case-operations-overview",
    ),

    path(
        "admin/evidence-custody/",
        R4JAdminEvidenceCustodyListView.as_view(),
        name="admin-evidence-custody-list",
    ),
    path(
        "admin/evidence-custody/<int:event_id>/review/",
        R4JAdminEvidenceCustodyReviewView.as_view(),
        name="admin-evidence-custody-review",
    ),

    # ====================================================
    # Admin — Criminals CRUD
    # ====================================================
    path(
        "admin/criminals/",
        R4JAdminCriminalListCreateView.as_view(),
        name="admin-criminal-list-create",
    ),
    path(
        "admin/criminals/<int:criminal_id>/",
        R4JAdminCriminalDetailView.as_view(),
        name="admin-criminal-detail",
    ),
    path(
        "admin/criminals/<int:criminal_id>/publish/",
        R4JAdminCriminalPublishView.as_view(),
        name="admin-criminal-publish",
    ),
    path(
        "admin/criminals/<int:criminal_id>/unpublish/",
        R4JAdminCriminalUnpublishView.as_view(),
        name="admin-criminal-unpublish",
    ),

    # ====================================================
    # Admin — Nested: Aliases
    # ====================================================
    path(
        "admin/criminals/<int:criminal_id>/aliases/",
        R4JAdminAliasListCreateView.as_view(),
        name="admin-alias-list-create",
    ),
    path(
        "admin/criminals/<int:criminal_id>/aliases/<int:alias_id>/",
        R4JAdminAliasDeleteView.as_view(),
        name="admin-alias-delete",
    ),

    # ====================================================
    # Admin — Nested: Phones
    # ====================================================
    path(
        "admin/criminals/<int:criminal_id>/phones/",
        R4JAdminPhoneListCreateView.as_view(),
        name="admin-phone-list-create",
    ),
    path(
        "admin/criminals/<int:criminal_id>/phones/<int:phone_id>/",
        R4JAdminPhoneDetailView.as_view(),
        name="admin-phone-detail",
    ),

    # ====================================================
    # Admin — Nested: Socials
    # ====================================================
    path(
        "admin/criminals/<int:criminal_id>/socials/",
        R4JAdminSocialListCreateView.as_view(),
        name="admin-social-list-create",
    ),
    path(
        "admin/criminals/<int:criminal_id>/socials/<int:social_id>/",
        R4JAdminSocialDetailView.as_view(),
        name="admin-social-detail",
    ),

    # ====================================================
    # Admin — Nested: Photos
    # ====================================================
    path(
        "admin/criminals/<int:criminal_id>/photos/",
        R4JAdminPhotoListCreateView.as_view(),
        name="admin-photo-list-create",
    ),
    path(
        "admin/criminals/<int:criminal_id>/photos/<int:photo_id>/",
        R4JAdminPhotoDetailView.as_view(),
        name="admin-photo-detail",
    ),
    path(
        "admin/criminals/<int:criminal_id>/photos/<int:photo_id>/set-primary/",
        R4JAdminPhotoSetPrimaryView.as_view(),
        name="admin-photo-set-primary",
    ),

    # ====================================================
    # Admin — Nested: Attachments
    # ====================================================
    path(
        "admin/criminals/<int:criminal_id>/attachments/",
        R4JAdminAttachmentListCreateView.as_view(),
        name="admin-attachment-list-create",
    ),
    path(
        "admin/criminals/<int:criminal_id>/attachments/<int:attachment_id>/",
        R4JAdminAttachmentDetailView.as_view(),
        name="admin-attachment-detail",
    ),

    # ====================================================
    # Admin — Field Visibility
    # ====================================================
    path(
        "admin/criminals/<int:criminal_id>/visibility/",
        R4JAdminFieldVisibilityListUpsertView.as_view(),
        name="admin-visibility-list-upsert",
    ),

    # ====================================================
    # Admin — Reports
    # ====================================================
    path(
        "admin/reports/",
        R4JAdminReportListView.as_view(),
        name="admin-report-list",
    ),
    path(
        "admin/reports/<int:report_id>/",
        R4JAdminReportDetailView.as_view(),
        name="admin-report-detail",
    ),
    path(
        "admin/reports/<int:report_id>/review/",
        R4JAdminReportReviewView.as_view(),
        name="admin-report-review",
    ),
    path(
        "admin/reports/<int:report_id>/cancel/approve/",
        R4JAdminReportCancelApproveView.as_view(),
        name="admin-report-cancel-approve",
    ),
    path(
        "admin/reports/<int:report_id>/cancel/reject/",
        R4JAdminReportCancelRejectView.as_view(),
        name="admin-report-cancel-reject",
    ),

    # ====================================================
    # Admin — Bounties
    # ====================================================
    path(
        "admin/bounties/",
        R4JAdminBountyListView.as_view(),
        name="admin-bounty-list",
    ),
    path(
        "admin/bounties/<int:bounty_id>/",
        R4JAdminBountyDetailView.as_view(),
        name="admin-bounty-detail",
    ),
    path(
        "admin/bounties/<int:bounty_id>/cancel/approve/",
        R4JAdminBountyCancelApproveView.as_view(),
        name="admin-bounty-cancel-approve",
    ),
    path(
        "admin/bounties/<int:bounty_id>/cancel/reject/",
        R4JAdminBountyCancelRejectView.as_view(),
        name="admin-bounty-cancel-reject",
    ),
]
